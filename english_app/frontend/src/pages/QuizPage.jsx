import React, { useState, useEffect, useContext } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { get, post } from '../api.js'
import { ProfileContext } from '../App.jsx'

export default function QuizPage() {
  const navigate = useNavigate()
  const { profile } = useContext(ProfileContext)

  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selectedOption, setSelectedOption] = useState(null)
  const [answered, setAnswered] = useState(false)
  const [results, setResults] = useState([])
  const [finished, setFinished] = useState(false)
  const [quizResult, setQuizResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const fetchQuestions = () => {
    setLoading(true)
    setError(null)
    setQuestions([])
    setCurrentIndex(0)
    setSelectedOption(null)
    setAnswered(false)
    setResults([])
    setFinished(false)
    setQuizResult(null)

    get('/quiz/questions')
      .then(data => {
        if (data.error) {
          setError(data.error)
        } else {
          setQuestions(data.questions || [])
        }
        setLoading(false)
      })
      .catch(() => {
        setError('퀴즈를 불러오는 데 실패했습니다.')
        setLoading(false)
      })
  }

  useEffect(() => {
    fetchQuestions()
  }, [])

  const handleOptionClick = (optionIndex) => {
    if (answered) return
    setSelectedOption(optionIndex)
    setAnswered(true)

    const q = questions[currentIndex]
    const isCorrect = optionIndex === q.correct_index
    const newResults = [...results, { word_id: q.word_id, correct: isCorrect }]
    setResults(newResults)
  }

  const handleNext = async () => {
    if (currentIndex + 1 >= questions.length) {
      // Submit quiz
      setSubmitting(true)
      try {
        const data = await post('/quiz/submit', { results })
        setQuizResult(data)
        setFinished(true)
      } catch (err) {
        console.error('Submit error:', err)
      } finally {
        setSubmitting(false)
      }
    } else {
      setCurrentIndex(prev => prev + 1)
      setSelectedOption(null)
      setAnswered(false)
    }
  }

  if (!profile) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="text-5xl mb-4">🔒</div>
        <h2 className="text-xl font-bold text-gray-700 mb-4">레벨 테스트를 먼저 진행해주세요.</h2>
        <Link
          to="/level-test"
          className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition"
        >
          레벨 테스트 하기
        </Link>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 flex justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="text-5xl mb-4">📚</div>
        <h2 className="text-xl font-bold text-gray-700 mb-3">{error}</h2>
        <Link
          to="/vocab"
          className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition"
        >
          단어 학습하러 가기
        </Link>
      </div>
    )
  }

  if (submitting) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent mx-auto mb-4"></div>
        <p className="text-gray-600">결과를 저장 중...</p>
      </div>
    )
  }

  if (finished && quizResult) {
    const pct = quizResult.accuracy_pct
    const emoji = pct >= 80 ? '🎉' : pct >= 60 ? '👍' : '💪'
    return (
      <div className="max-w-2xl mx-auto px-4 py-8 text-center">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-10">
          <div className="text-6xl mb-4">{emoji}</div>
          <h2 className="text-2xl font-bold text-gray-800 mb-6">퀴즈 완료!</h2>
          <div className="text-6xl font-bold text-indigo-600 mb-2">
            {quizResult.correct} <span className="text-3xl text-gray-400">/ {quizResult.total}</span>
          </div>
          <div className="text-lg text-gray-500 mb-8">정답률: {pct}%</div>
          <div className="flex justify-center gap-4">
            <button
              onClick={fetchQuestions}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition"
            >
              다시 풀기
            </button>
            <Link
              to="/vocab"
              className="bg-white hover:bg-gray-50 text-indigo-600 border border-indigo-300 font-semibold py-3 px-6 rounded-xl transition"
            >
              단어 학습
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-gray-500">
        퀴즈 문제가 없습니다.
      </div>
    )
  }

  const q = questions[currentIndex]
  const progress = (currentIndex / questions.length) * 100

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Progress */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-500 mb-2">
          <span>문제 {currentIndex + 1} / {questions.length}</span>
          <span>{q.type === 'meaning' ? '뜻 맞추기' : '영어 맞추기'}</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      </div>

      {/* Question */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 mb-6 text-center">
        <h2 className="text-2xl font-bold text-gray-800">{q.question}</h2>
      </div>

      {/* Options */}
      <div className="space-y-3 mb-6">
        {q.options.map((option, idx) => {
          let btnClass = 'w-full text-left p-4 rounded-xl border-2 font-medium transition '
          if (answered) {
            if (idx === q.correct_index) {
              btnClass += 'bg-green-50 border-green-400 text-green-800'
            } else if (idx === selectedOption && idx !== q.correct_index) {
              btnClass += 'bg-red-50 border-red-400 text-red-800'
            } else {
              btnClass += 'border-gray-200 text-gray-400 bg-gray-50 cursor-not-allowed'
            }
          } else {
            btnClass += 'border-gray-200 hover:border-indigo-400 hover:bg-indigo-50 text-gray-700 bg-white cursor-pointer'
          }

          return (
            <button
              key={idx}
              onClick={() => handleOptionClick(idx)}
              disabled={answered}
              className={btnClass}
            >
              <span className="font-bold text-gray-400 mr-3">{idx + 1}.</span>
              {option}
              {answered && idx === q.correct_index && <span className="ml-2">✓</span>}
              {answered && idx === selectedOption && idx !== q.correct_index && <span className="ml-2">✗</span>}
            </button>
          )
        })}
      </div>

      {/* Next button */}
      {answered && (
        <button
          onClick={handleNext}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition"
        >
          {currentIndex + 1 >= questions.length ? '결과 보기' : '다음 →'}
        </button>
      )}
    </div>
  )
}

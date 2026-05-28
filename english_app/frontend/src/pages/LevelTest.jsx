import React, { useState, useEffect, useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { get, post } from '../api.js'
import { ProfileContext } from '../App.jsx'

export default function LevelTest() {
  const navigate = useNavigate()
  const { setProfile } = useContext(ProfileContext)

  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState([])
  const [selectedOption, setSelectedOption] = useState(null)
  const [showFeedback, setShowFeedback] = useState(false)
  const [finished, setFinished] = useState(false)
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    get('/level-test/questions')
      .then(data => {
        setQuestions(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const handleOptionClick = (optionIndex) => {
    if (showFeedback) return

    setSelectedOption(optionIndex)
    setShowFeedback(true)

    const newAnswers = [...answers, optionIndex]

    setTimeout(() => {
      if (currentIndex + 1 >= questions.length) {
        // All questions answered
        setAnswers(newAnswers)
        submitTest(newAnswers)
      } else {
        setAnswers(newAnswers)
        setCurrentIndex(prev => prev + 1)
        setSelectedOption(null)
        setShowFeedback(false)
      }
    }, 1000)
  }

  const submitTest = async (finalAnswers) => {
    setSubmitting(true)
    try {
      const data = await post('/level-test/submit', { answers: finalAnswers })
      setResult(data)
      setProfile({ ...data, exists: true })
      setFinished(true)
    } catch (err) {
      console.error('Submit error:', err)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 flex justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent"></div>
      </div>
    )
  }

  if (submitting) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent mx-auto mb-4"></div>
        <p className="text-gray-600">결과를 분석 중입니다...</p>
      </div>
    )
  }

  if (finished && result) {
    const pct = Math.round((result.score / result.total) * 100)
    return (
      <div className="max-w-2xl mx-auto px-4 py-8 text-center">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-10">
          <div className="text-6xl mb-4">🎉</div>
          <h2 className="text-3xl font-bold text-gray-800 mb-2">테스트 완료!</h2>
          <div className="text-6xl font-bold text-indigo-600 my-6">
            {result.score} <span className="text-3xl text-gray-400">/ {result.total}</span>
          </div>
          <div className="text-lg text-gray-500 mb-2">정답률: {pct}%</div>
          <div className="inline-block bg-indigo-100 text-indigo-800 text-xl font-bold px-6 py-3 rounded-full my-4">
            레벨: {result.level_code} — {result.level_label}
          </div>
          <p className="text-gray-500 mb-8 mt-2">
            매일 <strong>{result.daily_vocab_count}개</strong>의 단어/숙어를 학습합니다.
          </p>
          <div className="text-4xl mb-6">
            {pct >= 80 ? '🌟🌟🌟' : pct >= 60 ? '⭐⭐' : '⭐'}
          </div>
          <button
            onClick={() => navigate('/vocab')}
            className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-8 rounded-xl transition text-lg"
          >
            학습 시작하기 →
          </button>
        </div>
      </div>
    )
  }

  if (questions.length === 0) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-gray-500">
        문제를 불러올 수 없습니다.
      </div>
    )
  }

  const q = questions[currentIndex]
  const progress = ((currentIndex) / questions.length) * 100

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-500 mb-2">
          <span>문제 {currentIndex + 1} / {questions.length}</span>
          <span>{Math.round(progress)}% 완료</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-6">
        <div className="inline-block text-xs font-semibold px-2 py-1 rounded-full mb-4 bg-indigo-50 text-indigo-600">
          {q.level === 'easy' ? '초급' : q.level === 'medium' ? '중급' : '고급'}
        </div>
        <h2 className="text-lg font-semibold text-gray-800 whitespace-pre-wrap leading-relaxed">
          {q.question}
        </h2>
      </div>

      <div className="space-y-3">
        {q.options.map((option, idx) => {
          let btnClass = 'w-full text-left p-4 rounded-xl border-2 font-medium transition '
          if (showFeedback && selectedOption === idx) {
            // Show the clicked button color (we don't know correct answer on frontend)
            btnClass += 'bg-blue-50 border-blue-400 text-blue-800'
          } else if (showFeedback) {
            btnClass += 'border-gray-200 text-gray-400 bg-gray-50 cursor-not-allowed'
          } else {
            btnClass += 'border-gray-200 hover:border-indigo-400 hover:bg-indigo-50 text-gray-700 cursor-pointer bg-white'
          }

          return (
            <button
              key={idx}
              onClick={() => handleOptionClick(idx)}
              disabled={showFeedback}
              className={btnClass}
            >
              <span className="font-bold text-gray-400 mr-3">{idx + 1}.</span>
              {option}
            </button>
          )
        })}
      </div>
    </div>
  )
}

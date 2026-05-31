import React, { useState, useEffect, useContext } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { get, post } from '../api.js'
import { ProfileContext } from '../App.jsx'

const speak = (text) => {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  try {
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    u.lang = 'en-US'
    u.rate = 0.85
    window.speechSynthesis.speak(u)
  } catch {
    // 음성 합성 미지원 브라우저 — 무시
  }
}

export default function VocabStudy() {
  const navigate = useNavigate()
  const { profile } = useContext(ProfileContext)

  const [words, setWords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [completed, setCompleted] = useState(false)
  const [dateInfo, setDateInfo] = useState(null)

  const loadWords = () => {
    setLoading(true)
    setError(null)
    get('/vocab/today')
      .then(data => {
        if (data.detail) {
          setError(data.detail)
        } else {
          setWords(data.words || [])
          setDateInfo({ date: data.date, level_code: data.level_code, level_label: data.level_label })
        }
        setLoading(false)
      })
      .catch(() => {
        setError('단어를 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요.')
        setLoading(false)
      })
  }

  useEffect(() => {
    loadWords()
  }, [])

  const handleMark = async (correct) => {
    if (words.length === 0) return
    const word = words[currentIndex]
    // 마킹 실패해도 학습 흐름은 끊기지 않도록 한다.
    try {
      await post('/vocab/mark', { word_id: word.id, correct })
    } catch {
      // 기록 실패는 무시하고 진행
    }

    if (currentIndex + 1 >= words.length) {
      setCompleted(true)
    } else {
      setCurrentIndex(prev => prev + 1)
      setFlipped(false)
    }
  }

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1)
      setFlipped(false)
    }
  }

  const handleNext = () => {
    if (currentIndex < words.length - 1) {
      setCurrentIndex(prev => prev + 1)
      setFlipped(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 flex flex-col items-center gap-4">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent"></div>
        <p className="text-gray-500 text-center">오늘의 단어를 불러오는 중...</p>
        <p className="text-gray-400 text-sm text-center">AI가 단어를 생성하는 첫 로딩은 30초 정도 걸릴 수 있어요</p>
      </div>
    )
  }

  if (error || !profile) {
    // 프로필은 있는데 단어 로딩이 실패한 경우 → 재시도 버튼 제공
    const canRetry = !!profile && !!error
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="text-5xl mb-4">⚠️</div>
        <h2 className="text-xl font-bold text-gray-700 mb-3">
          {error || '레벨 테스트를 먼저 진행해주세요.'}
        </h2>
        {canRetry ? (
          <button
            onClick={loadWords}
            className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition mt-4"
          >
            🔄 다시 시도
          </button>
        ) : (
          <Link
            to="/level-test"
            className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition mt-4"
          >
            레벨 테스트 하기
          </Link>
        )}
      </div>
    )
  }

  if (completed) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-10">
          <div className="text-6xl mb-4">🎊</div>
          <h2 className="text-2xl font-bold text-gray-800 mb-3">오늘의 단어 학습 완료!</h2>
          <p className="text-gray-500 mb-8">
            총 {words.length}개의 단어를 학습했습니다. 퀴즈로 복습해보세요!
          </p>
          <div className="flex flex-col gap-3 items-center">
            <button
              onClick={() => navigate('/quiz')}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-8 rounded-xl transition"
            >
              퀴즈 풀기 →
            </button>
            <button
              onClick={() => { setCompleted(false); setCurrentIndex(0); setFlipped(false) }}
              className="text-indigo-600 hover:text-indigo-800 text-sm underline"
            >
              다시 보기
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (words.length === 0) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-gray-500">
        오늘의 단어가 없습니다.
      </div>
    )
  }

  const word = words[currentIndex]

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-bold text-gray-800">오늘의 단어</h1>
        <div className="text-sm text-gray-500">
          {currentIndex + 1} / {words.length}
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-2 mb-8">
        <div
          className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
          style={{ width: `${((currentIndex + 1) / words.length) * 100}%` }}
        ></div>
      </div>

      {/* Flashcard */}
      <div className="card-flip mb-6 cursor-pointer" style={{ height: '340px' }} onClick={() => setFlipped(f => !f)}>
        <div className={`card-inner relative w-full h-full ${flipped ? 'flipped' : ''}`}>
          {/* Front */}
          <div className="card-face absolute inset-0 bg-white rounded-2xl shadow-sm border border-gray-100 p-8 flex flex-col justify-between">
            <div className="flex justify-between items-start">
              <span className={`text-xs font-semibold px-3 py-1 rounded-full ${word.type === 'idiom' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>
                {word.type === 'idiom' ? '숙어' : '단어'}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); speak(word.english) }}
                className="text-2xl hover:scale-110 transition-transform"
                title="발음 듣기"
              >
                🔊
              </button>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-gray-800 mb-3">{word.english}</div>
              <div className="text-lg text-gray-400 font-mono">{word.pronunciation}</div>
            </div>
            <div className="text-center text-sm text-gray-400">
              카드를 클릭하면 뜻을 볼 수 있어요 👆
            </div>
          </div>

          {/* Back */}
          <div className="card-face card-back absolute inset-0 bg-indigo-600 rounded-2xl shadow-sm p-8 flex flex-col justify-between">
            <div className="text-indigo-200 text-sm font-medium">{word.part_of_speech}</div>
            <div className="text-center">
              <div className="text-4xl font-bold text-white mb-4">{word.korean}</div>
              <div className="text-indigo-100 text-sm italic mb-2">"{word.example_en}"</div>
              <div className="text-indigo-200 text-sm">→ {word.example_ko}</div>
            </div>
            <div>
              {word.tip && (
                <div className="bg-indigo-500 rounded-xl px-4 py-2 text-indigo-100 text-xs">
                  💡 {word.tip}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={handlePrev}
          disabled={currentIndex === 0}
          className="text-2xl px-4 py-2 rounded-xl bg-white border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition"
        >
          ◀
        </button>
        <div className="flex gap-3">
          <button
            onClick={() => handleMark(false)}
            className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-white font-semibold py-2 px-5 rounded-xl transition"
          >
            <span>📝</span> 학습 중
          </button>
          <button
            onClick={() => handleMark(true)}
            className="flex items-center gap-2 bg-green-500 hover:bg-green-600 text-white font-semibold py-2 px-5 rounded-xl transition"
          >
            <span>✓</span> 알고 있음
          </button>
        </div>
        <button
          onClick={handleNext}
          disabled={currentIndex === words.length - 1}
          className="text-2xl px-4 py-2 rounded-xl bg-white border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition"
        >
          ▶
        </button>
      </div>

      {dateInfo && (
        <p className="text-center text-xs text-gray-400 mt-2">
          {dateInfo.date} · {dateInfo.level_label}
        </p>
      )}
    </div>
  )
}

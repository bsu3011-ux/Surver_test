import React, { useState, useEffect, useContext } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { get } from '../api.js'
import { ProfileContext } from '../App.jsx'

const LEVEL_COLORS = {
  A2: 'bg-green-100 text-green-800 border-green-200',
  B1: 'bg-blue-100 text-blue-800 border-blue-200',
  B2: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  C1: 'bg-orange-100 text-orange-800 border-orange-200',
  C2: 'bg-red-100 text-red-800 border-red-200',
}

const LEVEL_BG = {
  A2: 'from-green-500 to-green-700',
  B1: 'from-blue-500 to-blue-700',
  B2: 'from-yellow-500 to-yellow-700',
  C1: 'from-orange-500 to-orange-700',
  C2: 'from-red-500 to-red-700',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { profile } = useContext(ProfileContext)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    get('/dashboard')
      .then(data => {
        if (data.detail) {
          setError(data.detail)
        } else {
          setStats(data)
        }
        setLoading(false)
      })
      .catch(() => {
        setError('데이터를 불러올 수 없습니다.')
        setLoading(false)
      })
  }, [])

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

  if (error || !stats) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-gray-500">
        {error || '데이터가 없습니다.'}
      </div>
    )
  }

  const bgGradient = LEVEL_BG[stats.level_code] || 'from-indigo-500 to-indigo-700'

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Level badge */}
      <div className={`bg-gradient-to-br ${bgGradient} rounded-2xl p-8 text-white text-center mb-6 shadow-md`}>
        <div className="text-sm font-medium opacity-80 mb-1">나의 영어 레벨</div>
        <div className="text-5xl font-extrabold mb-2">{stats.level_code}</div>
        <div className="text-lg font-medium opacity-90">{stats.level_label}</div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
          <div className="text-3xl font-bold text-indigo-600 mb-1">{stats.total_words}</div>
          <div className="text-sm text-gray-500">학습 단어 수</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
          <div className="text-3xl font-bold text-indigo-600 mb-1">{stats.quiz_sessions}</div>
          <div className="text-sm text-gray-500">퀴즈 횟수</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
          <div className="text-3xl font-bold text-indigo-600 mb-1">{stats.avg_accuracy}%</div>
          <div className="text-sm text-gray-500">평균 정답률</div>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
          <div className="text-3xl font-bold text-indigo-600 mb-1">{stats.streak_days}일</div>
          <div className="text-sm text-gray-500">연속 학습일</div>
        </div>
      </div>

      {/* Streak note */}
      {stats.streak_days > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3 text-center mb-6 text-sm text-yellow-800">
          🔥 {stats.streak_days}일 연속 학습 중! 오늘도 화이팅!
        </div>
      )}

      {/* Quick actions */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-6">
        <h3 className="font-bold text-gray-700 mb-4">빠른 시작</h3>
        <div className="grid grid-cols-3 gap-3">
          <Link
            to="/vocab"
            className="flex flex-col items-center gap-2 p-4 bg-blue-50 hover:bg-blue-100 rounded-xl transition text-center"
          >
            <span className="text-2xl">📖</span>
            <span className="text-xs font-semibold text-blue-700">단어 학습</span>
          </Link>
          <Link
            to="/quiz"
            className="flex flex-col items-center gap-2 p-4 bg-green-50 hover:bg-green-100 rounded-xl transition text-center"
          >
            <span className="text-2xl">✅</span>
            <span className="text-xs font-semibold text-green-700">퀴즈</span>
          </Link>
          <Link
            to="/conversation"
            className="flex flex-col items-center gap-2 p-4 bg-purple-50 hover:bg-purple-100 rounded-xl transition text-center"
          >
            <span className="text-2xl">💬</span>
            <span className="text-xs font-semibold text-purple-700">회화 연습</span>
          </Link>
        </div>
      </div>

      {/* Retake level test */}
      <div className="text-center">
        <button
          onClick={() => navigate('/level-test')}
          className="text-sm text-gray-500 hover:text-indigo-600 border border-gray-200 hover:border-indigo-300 px-4 py-2 rounded-xl transition"
        >
          레벨 테스트 다시 받기
        </button>
      </div>
    </div>
  )
}

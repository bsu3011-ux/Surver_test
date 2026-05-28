import React, { useContext } from 'react'
import { Link } from 'react-router-dom'
import { ProfileContext } from '../App.jsx'

const LEVEL_COLORS = {
  A2: 'bg-green-100 text-green-800 border-green-200',
  B1: 'bg-blue-100 text-blue-800 border-blue-200',
  B2: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  C1: 'bg-orange-100 text-orange-800 border-orange-200',
  C2: 'bg-red-100 text-red-800 border-red-200',
}

const FEATURES = [
  {
    emoji: '📖',
    title: '단어 학습',
    description: '오늘의 단어를 플래시카드로 학습하세요.',
    link: '/vocab',
    color: 'border-blue-200 hover:border-blue-400',
  },
  {
    emoji: '✅',
    title: '퀴즈',
    description: '학습한 단어로 퀴즈를 풀어 실력을 확인하세요.',
    link: '/quiz',
    color: 'border-green-200 hover:border-green-400',
  },
  {
    emoji: '💬',
    title: 'AI 회화',
    description: 'AI와 영어 대화 연습을 해보세요.',
    link: '/conversation',
    color: 'border-purple-200 hover:border-purple-400',
  },
  {
    emoji: '📊',
    title: '대시보드',
    description: '학습 현황과 통계를 확인하세요.',
    link: '/dashboard',
    color: 'border-orange-200 hover:border-orange-400',
  },
]

export default function Home() {
  const { profile } = useContext(ProfileContext)

  if (!profile) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="text-6xl mb-6">🎓</div>
        <h1 className="text-3xl font-bold text-gray-800 mb-4">
          영어 학습 앱에 오신 것을 환영합니다!
        </h1>
        <p className="text-lg text-gray-500 mb-8">
          먼저 영어 레벨 테스트를 통해 나의 실력을 파악해보세요.
        </p>
        <p className="text-base text-gray-400 mb-10">
          레벨 테스트를 먼저 시작하세요
        </p>
        <Link
          to="/level-test"
          className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-4 px-10 rounded-xl transition text-lg shadow-md"
        >
          🚀 레벨 테스트 시작
        </Link>
      </div>
    )
  }

  const levelColorClass = LEVEL_COLORS[profile.level_code] || 'bg-gray-100 text-gray-800 border-gray-200'

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="text-center mb-10">
        <div className="text-5xl mb-4">👋</div>
        <h1 className="text-2xl font-bold text-gray-800 mb-3">오늘도 열심히 공부해봐요!</h1>
        <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-semibold ${levelColorClass}`}>
          <span>나의 레벨:</span>
          <span className="font-bold">{profile.level_code}</span>
          <span>—</span>
          <span>{profile.level_label}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {FEATURES.map(f => (
          <Link
            key={f.link}
            to={f.link}
            className={`bg-white rounded-2xl shadow-sm border-2 p-6 transition hover:shadow-md ${f.color}`}
          >
            <div className="text-4xl mb-3">{f.emoji}</div>
            <h2 className="text-lg font-bold text-gray-800 mb-1">{f.title}</h2>
            <p className="text-sm text-gray-500">{f.description}</p>
          </Link>
        ))}
      </div>

      <div className="mt-8 text-center">
        <Link
          to="/level-test"
          className="text-sm text-indigo-600 hover:text-indigo-800 underline"
        >
          레벨 테스트 다시 받기
        </Link>
      </div>
    </div>
  )
}

import React, { useContext } from 'react'
import { Link } from 'react-router-dom'
import { ProfileContext } from '../App.jsx'

const LEVEL_COLORS = {
  A2: 'bg-green-100 text-green-700 border-green-200',
  B1: 'bg-blue-100 text-blue-700 border-blue-200',
  B2: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  C1: 'bg-orange-100 text-orange-700 border-orange-200',
  C2: 'bg-red-100 text-red-700 border-red-200',
}

const FEATURES = [
  { emoji: '📖', title: '단어 학습', desc: '오늘의 단어 플래시카드', link: '/vocab', bg: 'bg-blue-50', text: 'text-blue-700' },
  { emoji: '✅', title: '퀴즈', desc: '배운 단어로 실력 테스트', link: '/quiz', bg: 'bg-green-50', text: 'text-green-700' },
  { emoji: '💬', title: 'AI 회화', desc: 'AI와 영어 대화 연습', link: '/conversation', bg: 'bg-purple-50', text: 'text-purple-700' },
  { emoji: '📊', title: '대시보드', desc: '학습 현황과 통계 보기', link: '/dashboard', bg: 'bg-orange-50', text: 'text-orange-700' },
]

export default function Home() {
  const { profile } = useContext(ProfileContext)

  if (!profile) {
    return (
      <div className="max-w-md mx-auto px-6 pt-16 pb-8 text-center">
        <div className="w-20 h-20 bg-indigo-100 rounded-full flex items-center justify-center text-4xl mx-auto mb-6">
          🎓
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-3">
          영어 학습 앱에 오신 걸 환영합니다
        </h1>
        <p className="text-gray-500 mb-8 leading-relaxed text-[15px]">
          레벨 테스트로 나의 영어 실력을 파악하고<br />
          맞춤형 학습을 시작해보세요.
        </p>
        <Link
          to="/level-test"
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3.5 px-8 rounded-2xl transition shadow-lg shadow-indigo-200 text-[15px]"
        >
          <span>🚀</span>
          <span>레벨 테스트 시작</span>
        </Link>
      </div>
    )
  }

  const levelColorClass = LEVEL_COLORS[profile.level_code] || 'bg-gray-100 text-gray-700 border-gray-200'

  return (
    <div className="max-w-2xl mx-auto px-4 pt-5 pb-6">
      {/* Greeting */}
      <div className="mb-5">
        <h1 className="text-xl font-bold text-gray-900">안녕하세요! 👋</h1>
        <div className="flex items-center gap-2 mt-1">
          <p className="text-gray-500 text-sm">오늘도 꾸준히 영어 공부 해봐요.</p>
          <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full border ${levelColorClass}`}>
            {profile.level_code}
          </span>
        </div>
      </div>

      {/* Feature grid */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        {FEATURES.map(f => (
          <Link
            key={f.link}
            to={f.link}
            className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm hover:shadow-md hover:border-indigo-200 transition active:scale-95"
          >
            <div className={`w-11 h-11 ${f.bg} rounded-xl flex items-center justify-center text-2xl mb-3`}>
              {f.emoji}
            </div>
            <h2 className={`font-bold text-[14px] ${f.text} mb-0.5`}>{f.title}</h2>
            <p className="text-xs text-gray-500 leading-relaxed">{f.desc}</p>
          </Link>
        ))}
      </div>

      {/* Wrong note shortcut */}
      <Link
        to="/wrong-note"
        className="flex items-center gap-3 bg-rose-50 border border-rose-100 rounded-2xl px-4 py-3.5 hover:bg-rose-100 active:scale-[0.98] transition mb-5"
      >
        <span className="text-2xl">📝</span>
        <div className="flex-1">
          <div className="text-sm font-bold text-rose-700">오답노트</div>
          <div className="text-xs text-rose-500">틀린 단어 모아보기</div>
        </div>
        <span className="text-rose-400 text-lg">›</span>
      </Link>

      {/* Retake */}
      <div className="text-center">
        <Link
          to="/level-test"
          className="text-xs text-gray-400 hover:text-indigo-600 transition underline underline-offset-2"
        >
          레벨 테스트 다시 받기
        </Link>
      </div>
    </div>
  )
}

import React, { useContext } from 'react'
import { NavLink } from 'react-router-dom'
import { ProfileContext } from '../App.jsx'

const LEVEL_COLORS = {
  A2: 'bg-green-100 text-green-700',
  B1: 'bg-blue-100 text-blue-700',
  B2: 'bg-yellow-100 text-yellow-700',
  C1: 'bg-orange-100 text-orange-700',
  C2: 'bg-red-100 text-red-700',
}

const TABS = [
  { to: '/', label: '홈', icon: '🏠', end: true },
  { to: '/vocab', label: '단어', icon: '📖' },
  { to: '/quiz', label: '퀴즈', icon: '✅' },
  { to: '/conversation', label: '회화', icon: '💬' },
  { to: '/dashboard', label: 'MY', icon: '📊' },
]

export default function NavBar() {
  const { profile } = useContext(ProfileContext)
  const levelColor = LEVEL_COLORS[profile?.level_code] || 'bg-gray-100 text-gray-700'

  const desktopLinkClass = ({ isActive }) =>
    `px-3 py-1.5 rounded-lg text-sm font-medium transition ${
      isActive ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    }`

  return (
    <>
      {/* Top header */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-sm border-b border-gray-100 shadow-sm">
        <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-1.5 select-none">
            <span className="text-xl">📚</span>
            <span className="text-[17px] font-bold text-indigo-700 tracking-tight">영어 학습</span>
          </NavLink>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-0.5">
            {TABS.map(t => (
              <NavLink key={t.to} to={t.to} end={t.end} className={desktopLinkClass}>
                {t.label}
              </NavLink>
            ))}
            <NavLink to="/wrong-note" className={desktopLinkClass}>오답노트</NavLink>
          </nav>

          {profile && (
            <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${levelColor}`}>
              {profile.level_code}
            </span>
          )}
        </div>
      </header>

      {/* Mobile bottom tab bar */}
      <nav
        className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-white border-t border-gray-200"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="grid grid-cols-5 h-16">
          {TABS.map(t => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-0.5 transition-colors ${
                  isActive ? 'text-indigo-600' : 'text-gray-400'
                }`
              }
            >
              <span className="text-2xl leading-none">{t.icon}</span>
              <span className="text-[10px] font-semibold">{t.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </>
  )
}

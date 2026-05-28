import React, { useContext } from 'react'
import { NavLink } from 'react-router-dom'
import { ProfileContext } from '../App.jsx'

const LEVEL_COLORS = {
  A2: 'bg-green-100 text-green-800',
  B1: 'bg-blue-100 text-blue-800',
  B2: 'bg-yellow-100 text-yellow-800',
  C1: 'bg-orange-100 text-orange-800',
  C2: 'bg-red-100 text-red-800',
}

export default function NavBar() {
  const { profile } = useContext(ProfileContext)

  const linkClass = ({ isActive }) =>
    `text-sm font-medium px-3 py-2 rounded-lg transition ${
      isActive
        ? 'bg-indigo-100 text-indigo-700'
        : 'text-gray-600 hover:text-indigo-600 hover:bg-indigo-50'
    }`

  return (
    <nav className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
        <NavLink to="/" className="text-xl font-bold text-indigo-700 flex items-center gap-2">
          <span>📚</span>
          <span>영어 학습</span>
        </NavLink>

        <div className="flex items-center gap-1">
          <NavLink to="/" className={linkClass} end>홈</NavLink>
          <NavLink to="/vocab" className={linkClass}>단어학습</NavLink>
          <NavLink to="/quiz" className={linkClass}>퀴즈</NavLink>
          <NavLink to="/conversation" className={linkClass}>회화연습</NavLink>
          <NavLink to="/dashboard" className={linkClass}>대시보드</NavLink>

          {profile && (
            <span className={`ml-2 text-xs font-bold px-2 py-1 rounded-full ${LEVEL_COLORS[profile.level_code] || 'bg-gray-100 text-gray-700'}`}>
              {profile.level_code}
            </span>
          )}
        </div>
      </div>
    </nav>
  )
}

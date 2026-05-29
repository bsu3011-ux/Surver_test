import React, { createContext, useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import Home from './pages/Home.jsx'
import LevelTest from './pages/LevelTest.jsx'
import VocabStudy from './pages/VocabStudy.jsx'
import QuizPage from './pages/QuizPage.jsx'
import Conversation from './pages/Conversation.jsx'
import Dashboard from './pages/Dashboard.jsx'
import WrongNote from './pages/WrongNote.jsx'
import { get } from './api.js'

export const ProfileContext = createContext(null)

export default function App() {
  const [profile, setProfile] = useState(null)
  const [profileLoaded, setProfileLoaded] = useState(false)

  useEffect(() => {
    get('/profile')
      .then(data => {
        if (data.exists) {
          setProfile(data)
        } else {
          setProfile(null)
        }
      })
      .catch(() => setProfile(null))
      .finally(() => setProfileLoaded(true))
  }, [])

  if (!profileLoaded) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent"></div>
      </div>
    )
  }

  return (
    <ProfileContext.Provider value={{ profile, setProfile }}>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-50">
          <NavBar />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/level-test" element={<LevelTest />} />
            <Route path="/vocab" element={<VocabStudy />} />
            <Route path="/quiz" element={<QuizPage />} />
            <Route path="/conversation" element={<Conversation />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/wrong-note" element={<WrongNote />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ProfileContext.Provider>
  )
}

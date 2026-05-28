import React, { useState, useEffect, useRef, useContext } from 'react'
import { post } from '../api.js'
import { ProfileContext } from '../App.jsx'

const TOPICS = [
  { key: 'daily', label: '일상 대화', emoji: '☀️', desc: '인사, 취미, 날씨, 일상 활동' },
  { key: 'travel', label: '여행', emoji: '✈️', desc: '호텔 예약, 길 찾기, 식당, 관광' },
  { key: 'business', label: '비즈니스', emoji: '💼', desc: '이메일, 회의, 프레젠테이션, 협상' },
  { key: 'interview', label: '취업 면접', emoji: '🎯', desc: '자기소개, 장단점, 커리어 목표' },
]

const GREETINGS = {
  daily: "Hi there! How's your day going? Let's chat about everyday life!",
  travel: "Hello! Are you planning a trip somewhere? I'd love to help you practice travel English!",
  business: "Good day! Let's practice some professional English for the workplace. How can I help you?",
  interview: "Welcome! I'll be your interviewer today. Please start by introducing yourself briefly.",
}

export default function Conversation() {
  const { profile } = useContext(ProfileContext)
  const levelCode = profile?.level_code || 'B1'

  const [selectedTopic, setSelectedTopic] = useState(null)
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, loading])

  const handleTopicSelect = (topic) => {
    setSelectedTopic(topic.key)
    setMessages([
      {
        role: 'assistant',
        content: GREETINGS[topic.key],
        correction: null,
      }
    ])
    setInputText('')
  }

  const handleSend = async () => {
    const text = inputText.trim()
    if (!text || loading) return

    const userMessage = { role: 'user', content: text, correction: null }
    const newMessages = [...messages, userMessage]
    setMessages(newMessages)
    setInputText('')
    setLoading(true)

    // Build API messages (without correction field)
    const apiMessages = newMessages.map(m => ({ role: m.role, content: m.content }))

    try {
      const data = await post('/conversation/message', {
        messages: apiMessages,
        topic: selectedTopic,
        level_code: levelCode,
      })

      // Attach correction to the user message
      const updatedMessages = newMessages.map((m, i) => {
        if (i === newMessages.length - 1 && m.role === 'user') {
          return { ...m, correction: data.correction }
        }
        return m
      })

      // Add assistant reply
      updatedMessages.push({
        role: 'assistant',
        content: data.reply || '...',
        correction: null,
      })

      setMessages(updatedMessages)
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '죄송합니다, 오류가 발생했습니다. 다시 시도해주세요.',
        correction: null,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!selectedTopic) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">💬</div>
          <h1 className="text-2xl font-bold text-gray-800 mb-2">AI 회화 연습</h1>
          <p className="text-gray-500">주제를 선택하고 영어 대화를 연습해보세요.</p>
          {profile && (
            <p className="text-sm text-indigo-600 mt-1">현재 레벨: {levelCode}</p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          {TOPICS.map(topic => (
            <button
              key={topic.key}
              onClick={() => handleTopicSelect(topic)}
              className="bg-white rounded-2xl shadow-sm border-2 border-gray-100 hover:border-indigo-400 p-6 text-left transition hover:shadow-md"
            >
              <div className="text-4xl mb-3">{topic.emoji}</div>
              <h2 className="text-lg font-bold text-gray-800 mb-1">{topic.label}</h2>
              <p className="text-sm text-gray-500">{topic.desc}</p>
            </button>
          ))}
        </div>
      </div>
    )
  }

  const topicInfo = TOPICS.find(t => t.key === selectedTopic)

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col" style={{ height: 'calc(100vh - 80px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{topicInfo?.emoji}</span>
          <h1 className="text-lg font-bold text-gray-800">{topicInfo?.label}</h1>
          <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-semibold">{levelCode}</span>
        </div>
        <button
          onClick={() => { setSelectedTopic(null); setMessages([]) }}
          className="text-sm text-gray-500 hover:text-indigo-600 border border-gray-200 px-3 py-1.5 rounded-lg hover:border-indigo-300 transition"
        >
          주제 변경
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-white rounded-2xl border border-gray-100 shadow-sm p-4 mb-4 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx}>
            {msg.role === 'user' ? (
              <div className="flex flex-col items-end gap-1">
                <div className="max-w-xs lg:max-w-md">
                  <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
                    {msg.content}
                  </div>
                  {msg.correction?.has_error && (
                    <div className="mt-1 bg-yellow-50 border border-yellow-200 rounded-xl px-3 py-2 text-xs">
                      <div className="font-semibold text-yellow-800 mb-1">✏️ 수정 제안</div>
                      <div className="text-red-600 line-through">{msg.correction.original}</div>
                      <div className="text-green-700 font-medium">→ {msg.correction.corrected}</div>
                      {msg.correction.explanation && (
                        <div className="text-gray-600 mt-1">{msg.correction.explanation}</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-start">
                <div className="max-w-xs lg:max-w-md">
                  <div className="flex items-center gap-1 mb-1">
                    <span className="text-xs text-gray-400">AI</span>
                  </div>
                  <div className="bg-gray-100 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed">
                    {msg.content}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start">
            <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef}></div>
      </div>

      {/* Input */}
      <div className="flex gap-3 shrink-0">
        <input
          ref={inputRef}
          type="text"
          value={inputText}
          onChange={e => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="영어로 메시지를 입력하세요..."
          className="flex-1 border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:bg-gray-50"
        />
        <button
          onClick={handleSend}
          disabled={!inputText.trim() || loading}
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-5 py-3 rounded-xl transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          보내기
        </button>
      </div>
    </div>
  )
}

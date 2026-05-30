import React, { useState, useEffect, useRef, useContext } from 'react'
import { post } from '../api.js'
import { ProfileContext } from '../App.jsx'

const ALL_TOPICS = [
  { key: 'daily',           label: '일상 대화',      emoji: '☀️', desc: '인사, 취미, 날씨, 일상 활동',               toeic: false },
  { key: 'travel',          label: '여행',            emoji: '✈️', desc: '호텔 예약, 길 찾기, 식당, 관광',           toeic: false },
  { key: 'business',        label: '비즈니스',        emoji: '💼', desc: '이메일, 회의, 프레젠테이션, 협상',         toeic: false },
  { key: 'interview',       label: '취업 면접',       emoji: '🎯', desc: '자기소개, 장단점, 커리어 목표',            toeic: false },
  { key: 'toeic_picture',   label: '사진 묘사',       emoji: '🖼️', desc: 'TOEIC Speaking Part 1 — 사진 속 상황 묘사', toeic: true },
  { key: 'toeic_opinion',   label: '의견 표현',       emoji: '💡', desc: 'TOEIC Speaking Part 5 — 찬반 의견 + 이유 2가지', toeic: true },
  { key: 'toeic_solution',  label: '문제 해결 제안',  emoji: '🔧', desc: 'TOEIC Speaking Part 4 — 불만 메시지에 해결책 제안', toeic: true },
  { key: 'toeic_respond',   label: '질문 응답',       emoji: '🎙️', desc: 'TOEIC Speaking Part 3 — 인터뷰·설문 답변 연습', toeic: true },
]

const GREETINGS = {
  daily:          "Hi there! How's your day going? Let's chat about everyday life!",
  travel:         "Hello! Are you planning a trip somewhere? I'd love to help you practice travel English!",
  business:       "Good day! Let's practice some professional English for the workplace. How can I help you?",
  interview:      "Welcome! I'll be your interviewer today. Please start by introducing yourself briefly.",
  toeic_picture:  "Let's practice TOEIC Speaking Part 1 — Picture Description! I'll describe a scene and you try to describe it too, or I'll give you feedback on your description. Ready? Describe this: 'A woman is working at her desk in a busy open-plan office.'",
  toeic_opinion:  "Let's practice TOEIC Speaking Part 5 — Express an Opinion! I'll give you a topic and you should state your opinion clearly with at least TWO reasons. Ready? Topic: 'Do you think working from home is more productive than working in an office?'",
  toeic_solution: "Let's practice TOEIC Speaking Part 4 — Propose a Solution! Here's the situation: 'You received a voicemail from a customer named Mr. Kim. He ordered a laptop two weeks ago but it hasn't arrived yet, and he has an important meeting tomorrow.' Please respond and propose a solution.",
  toeic_respond:  "Let's practice TOEIC Speaking Part 3 — Respond to Questions! Imagine you are being interviewed about your work habits. Question 1: How many hours a day do you usually spend working, and what time do you typically start your workday?",
}

export default function Conversation() {
  const { profile } = useContext(ProfileContext)
  const levelCode = profile?.level_code || 'B1'
  const learningMode = profile?.learning_mode || 'general'

  const TOPICS = learningMode === 'toeic_speaking'
    ? ALL_TOPICS.filter(t => t.toeic || t.key === 'business' || t.key === 'interview')
    : ALL_TOPICS.filter(t => !t.toeic)

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
    const toeicTopics = TOPICS.filter(t => t.toeic)
    const generalTopics = TOPICS.filter(t => !t.toeic)

    const TopicCard = ({ topic }) => (
      <button
        key={topic.key}
        onClick={() => handleTopicSelect(topic)}
        className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md hover:border-indigo-300 p-4 text-left transition active:scale-95"
      >
        <div className="text-3xl mb-2">{topic.emoji}</div>
        <h2 className="text-[15px] font-bold text-gray-800 mb-0.5">{topic.label}</h2>
        <p className="text-xs text-gray-500 leading-relaxed">{topic.desc}</p>
      </button>
    )

    return (
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-5">
          <h1 className="text-xl font-bold text-gray-900">AI 회화 연습 💬</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            주제를 선택하고 영어 대화를 연습해보세요.
            {profile && <span className="ml-1 text-indigo-600 font-semibold">({levelCode})</span>}
          </p>
        </div>

        {learningMode === 'toeic_speaking' && toeicTopics.length > 0 && (
          <>
            <p className="text-xs font-bold text-rose-500 uppercase tracking-wider mb-2">TOEIC Speaking 유형별</p>
            <div className="grid grid-cols-2 gap-3 mb-5">
              {toeicTopics.map(t => <TopicCard key={t.key} topic={t} />)}
            </div>
            {generalTopics.length > 0 && (
              <p className="text-xs font-bold text-indigo-500 uppercase tracking-wider mb-2">비즈니스 회화</p>
            )}
          </>
        )}

        {generalTopics.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            {generalTopics.map(t => <TopicCard key={t.key} topic={t} />)}
          </div>
        )}
      </div>
    )
  }

  const topicInfo = ALL_TOPICS.find(t => t.key === selectedTopic)

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

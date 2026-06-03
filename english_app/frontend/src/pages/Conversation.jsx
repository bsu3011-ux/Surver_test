import React, { useState, useEffect, useRef, useContext, useCallback } from 'react'
import { post } from '../api.js'
import { ProfileContext } from '../App.jsx'

const ALL_TOPICS = [
  { key: 'daily',          label: '일상 대화',     emoji: '☀️', desc: '인사, 취미, 날씨, 일상 활동',                  toeic: false },
  { key: 'travel',         label: '여행',           emoji: '✈️', desc: '호텔 예약, 길 찾기, 식당, 관광',              toeic: false },
  { key: 'business',       label: '비즈니스',       emoji: '💼', desc: '이메일, 회의, 프레젠테이션, 협상',            toeic: false },
  { key: 'interview',      label: '취업 면접',      emoji: '🎯', desc: '자기소개, 장단점, 커리어 목표',               toeic: false },
  { key: 'toeic_picture',  label: '사진 묘사',      emoji: '🖼️', desc: 'TOEIC Speaking Part 1 — 사진 속 상황 묘사',  toeic: true  },
  { key: 'toeic_opinion',  label: '의견 표현',      emoji: '💡', desc: 'TOEIC Speaking Part 5 — 찬반 의견 + 이유 2가지', toeic: true },
  { key: 'toeic_solution', label: '문제 해결 제안', emoji: '🔧', desc: 'TOEIC Speaking Part 4 — 해결책 제안',         toeic: true  },
  { key: 'toeic_respond',  label: '질문 응답',      emoji: '🎙️', desc: 'TOEIC Speaking Part 3 — 인터뷰·설문 답변',   toeic: true  },
]

const GREETINGS = {
  daily:          "Hi there! How's your day going? Let's chat about everyday life!",
  travel:         "Hello! Are you planning a trip somewhere? I'd love to help you practice travel English!",
  business:       "Good day! Let's practice professional English for the workplace. How can I help you?",
  interview:      "Welcome! I'll be your interviewer today. Please start by introducing yourself briefly.",
  toeic_picture:  "Let's practice TOEIC Speaking Part 1 — Picture Description! Describe this scene: 'A woman is working at her desk in a busy open-plan office.'",
  toeic_opinion:  "Let's practice TOEIC Speaking Part 5! Topic: 'Do you think working from home is more productive than working in an office?' State your opinion with TWO reasons.",
  toeic_solution: "Let's practice TOEIC Speaking Part 4! Situation: 'A customer named Mr. Kim ordered a laptop two weeks ago but it hasn't arrived. He has an important meeting tomorrow.' Please respond and propose a solution.",
  toeic_respond:  "Let's practice TOEIC Speaking Part 3! Question 1: How many hours a day do you usually work, and what time do you typically start your workday?",
}

const getSR = () => window.SpeechRecognition || window.webkitSpeechRecognition

// ── TTS ──────────────────────────────────────────────────────────
const speakText = (text) => {
  if (!window.speechSynthesis) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.lang  = 'en-US'
  u.rate  = 0.88
  u.pitch = 1
  window.speechSynthesis.speak(u)
}

const stopSpeaking = () => window.speechSynthesis?.cancel()

export default function Conversation() {
  const { profile }   = useContext(ProfileContext)
  const levelCode     = profile?.level_code    || 'B1'
  const learningMode  = profile?.learning_mode || 'general'

  const TOPICS = learningMode === 'toeic_speaking'
    ? ALL_TOPICS.filter(t => t.toeic || t.key === 'business' || t.key === 'interview')
    : ALL_TOPICS.filter(t => !t.toeic)

  const [selectedTopic, setSelectedTopic] = useState(null)
  const [messages,      setMessages]      = useState([])
  const [inputText,     setInputText]     = useState('')
  const [interimText,   setInterimText]   = useState('')
  const [loading,       setLoading]       = useState(false)
  const [isRecording,   setIsRecording]   = useState(false)
  const [srSupported,   setSrSupported]   = useState(false)
  const [autoSpeak,     setAutoSpeak]     = useState(true)   // AI 메시지 자동 읽기
  const [micError,      setMicError]      = useState(null)   // 권한 거부 메시지

  const messagesEndRef = useRef(null)
  const inputRef       = useRef(null)
  const recognitionRef = useRef(null)

  useEffect(() => {
    setSrSupported(!!getSR())
    return () => {
      recognitionRef.current?.stop()
      stopSpeaking()
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, interimText])

  // AI 메시지 자동 읽기
  useEffect(() => {
    if (!autoSpeak || messages.length === 0) return
    const last = messages[messages.length - 1]
    if (last.role === 'assistant') speakText(last.content)
  }, [messages, autoSpeak])

  // ── 마이크 권한 요청 후 녹음 시작 ────────────────────────────────
  const startRecording = useCallback(() => {
    const SR = getSR()
    if (!SR) return

    const r = new SR()
    r.lang           = 'en-US'
    r.interimResults = true
    r.continuous     = false

    r.onstart  = () => setIsRecording(true)

    r.onresult = (e) => {
      let finalText = '', interimT = ''
      for (let i = 0; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) finalText += t
        else interimT += t
      }
      if (finalText) {
        setInputText(prev => (prev ? prev + ' ' : '') + finalText.trim())
        setInterimText('')
      } else {
        setInterimText(interimT)
      }
    }

    r.onend   = () => { setIsRecording(false); setInterimText('') }
    r.onerror = (ev) => {
      setIsRecording(false); setInterimText('')
      if (ev.error === 'not-allowed')
        setMicError('마이크 권한이 거부됐습니다. 브라우저 주소창의 자물쇠 아이콘을 눌러 마이크를 허용해주세요.')
    }

    recognitionRef.current = r
    r.start()
  }, [])

  const toggleRecording = async () => {
    if (isRecording) {
      recognitionRef.current?.stop()
      return
    }

    setMicError(null)
    stopSpeaking() // 읽는 중이면 멈추고 녹음

    // getUserMedia로 먼저 권한 요청 — 브라우저가 명시적 허용 다이얼로그를 띄움
    if (navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach(t => t.stop()) // 스트림 즉시 해제, 권한만 확보
      } catch (err) {
        const denied = err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'
        setMicError(
          denied
            ? '마이크 권한이 거부됐습니다. 브라우저 주소창의 자물쇠 아이콘을 눌러 마이크를 허용해주세요.'
            : '마이크를 사용할 수 없습니다. 장치를 확인해주세요.'
        )
        return
      }
    }

    startRecording()
  }

  // ── 주제 선택 ─────────────────────────────────────────────────
  const handleTopicSelect = (topic) => {
    setSelectedTopic(topic.key)
    const greeting = { role: 'assistant', content: GREETINGS[topic.key], correction: null, pronunciation: null }
    setMessages([greeting])
    setInputText(''); setInterimText(''); setMicError(null)
  }

  // ── 메시지 전송 ───────────────────────────────────────────────
  const handleSend = async () => {
    const text = inputText.trim()
    if (!text || loading) return

    stopSpeaking()
    const userMsg     = { role: 'user', content: text, correction: null, pronunciation: null }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInputText('')
    setLoading(true)

    const apiMessages = newMessages.map(m => ({ role: m.role, content: m.content }))

    try {
      const data = await post('/conversation/message', {
        messages: apiMessages, topic: selectedTopic, level_code: levelCode,
      })
      const updated = newMessages.map((m, i) =>
        i === newMessages.length - 1 && m.role === 'user'
          ? { ...m, correction: data.correction, pronunciation: data.pronunciation }
          : m
      )
      updated.push({ role: 'assistant', content: data.reply || '...', correction: null, pronunciation: null })
      setMessages(updated)
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant', content: '죄송합니다, 오류가 발생했습니다. 다시 시도해주세요.',
        correction: null, pronunciation: null,
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  // ── 주제 선택 화면 ────────────────────────────────────────────
  if (!selectedTopic) {
    const toeicTopics   = TOPICS.filter(t => t.toeic)
    const generalTopics = TOPICS.filter(t => !t.toeic)

    const TopicCard = ({ topic }) => (
      <button onClick={() => handleTopicSelect(topic)}
        className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md hover:border-indigo-300 p-4 text-left transition active:scale-95">
        <div className="text-3xl mb-2">{topic.emoji}</div>
        <h2 className="text-[15px] font-bold text-gray-800 mb-0.5">{topic.label}</h2>
        <p className="text-xs text-gray-500 leading-relaxed">{topic.desc}</p>
      </button>
    )

    return (
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="mb-4">
          <h1 className="text-xl font-bold text-gray-900">AI 스피킹 코치 🎙️</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            주제를 선택하고 영어로 말해보세요. AI가 발음·문법을 교정해 드립니다.
            {profile && <span className="ml-1 text-indigo-600 font-semibold">({levelCode})</span>}
          </p>
          <div className="flex flex-wrap gap-2 mt-2">
            {srSupported ? (
              <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-3 py-1">
                🎤 음성 입력 지원
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-full px-3 py-1">
                ⌨️ 텍스트 입력 (이 브라우저는 음성 미지원)
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-3 py-1">
              🔊 AI 메시지 자동 읽기
            </span>
          </div>
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

  // ── 채팅 화면 ─────────────────────────────────────────────────
  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col" style={{ height: 'calc(100vh - 80px)' }}>

      {/* 헤더 */}
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{topicInfo?.emoji}</span>
          <h1 className="text-lg font-bold text-gray-800">{topicInfo?.label}</h1>
          <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-semibold">{levelCode}</span>
        </div>
        <div className="flex items-center gap-2">
          {/* 자동 읽기 토글 */}
          <button
            onClick={() => { setAutoSpeak(v => !v); stopSpeaking() }}
            title={autoSpeak ? '자동 읽기 끄기' : '자동 읽기 켜기'}
            className={`text-lg w-8 h-8 rounded-lg flex items-center justify-center transition
              ${autoSpeak ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'}`}
          >
            {autoSpeak ? '🔊' : '🔇'}
          </button>
          <button
            onClick={() => { setSelectedTopic(null); setMessages([]); setInputText(''); stopSpeaking() }}
            className="text-sm text-gray-500 hover:text-indigo-600 border border-gray-200 px-3 py-1.5 rounded-lg hover:border-indigo-300 transition"
          >
            주제 변경
          </button>
        </div>
      </div>

      {/* 메시지 영역 */}
      <div className="flex-1 overflow-y-auto bg-white rounded-2xl border border-gray-100 shadow-sm p-4 mb-3 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx}>
            {msg.role === 'user' ? (
              /* ── 내 말풍선 ── */
              <div className="flex flex-col items-end gap-1">
                <div className="max-w-[80%]">
                  <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
                    {msg.content}
                  </div>

                  {/* 문법 교정 */}
                  {msg.correction?.has_error && (
                    <div className="mt-1.5 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-xs">
                      <div className="font-semibold text-amber-700 mb-1">✏️ 문법 교정</div>
                      <div className="text-red-500 line-through mb-0.5">{msg.correction.original}</div>
                      <div className="text-green-700 font-semibold">→ {msg.correction.corrected}</div>
                      {msg.correction.explanation && (
                        <div className="text-gray-600 mt-1">{msg.correction.explanation}</div>
                      )}
                    </div>
                  )}

                  {/* 발음 교정 */}
                  {msg.pronunciation?.has_tip && msg.pronunciation.words?.length > 0 && (
                    <div className="mt-1.5 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2 text-xs">
                      <div className="font-semibold text-blue-700 mb-1.5">🗣️ 발음 교정</div>
                      <div className="space-y-2">
                        {msg.pronunciation.words.map((pw, i) => (
                          <div key={i}>
                            <span className="font-bold text-blue-800 bg-blue-100 px-1.5 py-0.5 rounded">{pw.word}</span>
                            {pw.ipa && <span className="text-blue-500 font-mono ml-1.5">{pw.ipa}</span>}
                            {/* 단어 발음 듣기 */}
                            <button
                              onClick={() => speakText(pw.word)}
                              className="ml-1.5 text-blue-400 hover:text-blue-600"
                              title="발음 듣기"
                            >🔊</button>
                            <div className="text-gray-700 mt-0.5">{pw.tip}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              /* ── AI 말풍선 ── */
              <div className="flex flex-col items-start">
                <div className="max-w-[80%]">
                  <div className="flex items-center gap-1 mb-1">
                    <span className="text-xs font-semibold text-indigo-400">AI 코치</span>
                  </div>
                  <div className="relative group">
                    <div className="bg-gray-100 text-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed">
                      {msg.content}
                    </div>
                    {/* 다시 읽기 버튼 */}
                    <button
                      onClick={() => speakText(msg.content)}
                      className="absolute -right-8 top-1/2 -translate-y-1/2 text-gray-300 hover:text-indigo-500 transition text-lg"
                      title="다시 읽기"
                    >
                      🔊
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* AI 응답 대기 */}
        {loading && (
          <div className="flex items-start">
            <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1">
                {[0, 150, 300].map(d => (
                  <div key={d} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 마이크 권한 에러 */}
      {micError && (
        <div className="shrink-0 mb-2 flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl px-3 py-2 text-xs text-red-700">
          <span className="shrink-0">⚠️</span>
          <span>{micError}</span>
          <button onClick={() => setMicError(null)} className="ml-auto text-red-400 hover:text-red-600 shrink-0">✕</button>
        </div>
      )}

      {/* 입력 영역 */}
      <div className="shrink-0 space-y-2">
        {/* 음성 인식 중 미리보기 */}
        {(isRecording || interimText) && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse shrink-0" />
            <span className="text-sm text-red-700 italic flex-1 min-h-[20px]">
              {interimText || '듣고 있어요...'}
            </span>
          </div>
        )}

        <div className="flex gap-2">
          {/* 마이크 버튼 */}
          {srSupported && (
            <button
              onClick={toggleRecording}
              disabled={loading}
              title={isRecording ? '녹음 중단' : '음성 입력 (마이크 권한 필요)'}
              className={`shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-xl transition
                ${isRecording
                  ? 'bg-red-500 hover:bg-red-600 text-white shadow-lg shadow-red-200'
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
                } disabled:opacity-40`}
            >
              {isRecording ? '⏹' : '🎤'}
            </button>
          )}

          {/* 텍스트 입력 */}
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            placeholder={isRecording ? '음성으로 입력 중...' : '영어로 말하거나 입력하세요...'}
            className="flex-1 border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:bg-gray-50"
          />

          {/* 전송 버튼 */}
          <button
            onClick={handleSend}
            disabled={!inputText.trim() || loading}
            className="shrink-0 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-3 rounded-xl transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            전송
          </button>
        </div>
      </div>
    </div>
  )
}

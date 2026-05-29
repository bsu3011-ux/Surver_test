import React, { useState, useEffect, useContext } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../api.js'
import { ProfileContext } from '../App.jsx'

function AccuracyBar({ accuracy }) {
  if (accuracy === null) return <p className="text-xs text-gray-400 mt-1">아직 복습 안 함</p>
  const color = accuracy >= 70 ? 'bg-green-500' : accuracy >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="w-full bg-gray-100 rounded-full h-1.5 mt-2">
      <div className={`h-1.5 rounded-full transition-all duration-500 ${color}`} style={{ width: `${accuracy}%` }} />
    </div>
  )
}

function WordCard({ word }) {
  const acc = word.accuracy
  const dot = acc === null ? '⚪' : acc >= 70 ? '🟢' : acc >= 40 ? '🟡' : '🔴'
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="bg-white rounded-xl border border-gray-100 p-4 cursor-pointer hover:shadow-sm transition"
      onClick={() => setExpanded(v => !v)}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span>{dot}</span>
          <span className="font-bold text-gray-800 truncate">{word.english}</span>
          <span className="text-xs text-gray-400 hidden sm:inline">{word.part_of_speech}</span>
        </div>
        <div className="text-sm text-gray-500 ml-2 whitespace-nowrap">
          {acc !== null ? `${acc}%` : '미학습'}
          {word.review_count > 0 && <span className="text-gray-400"> ({word.review_count}회)</span>}
        </div>
      </div>

      <p className="text-gray-600 text-sm mt-1">{word.korean}</p>
      <AccuracyBar accuracy={acc} />

      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-100 space-y-1">
          {word.example_en && <p className="text-sm text-gray-600 italic">"{word.example_en}"</p>}
          {word.example_ko && <p className="text-sm text-gray-400">→ {word.example_ko}</p>}
        </div>
      )}
    </div>
  )
}

export default function WrongNote() {
  const { profile } = useContext(ProfileContext)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('wrong')

  useEffect(() => {
    get('/vocab/stats')
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (!profile) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="text-5xl mb-4">🔒</div>
        <h2 className="text-xl font-bold text-gray-700 mb-4">레벨 테스트를 먼저 진행해주세요.</h2>
        <Link to="/level-test" className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-xl transition">
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

  const words = data?.words || []
  const wrongWords = words.filter(w => w.accuracy !== null && w.accuracy < 60)
  const displayWords = tab === 'wrong' ? wrongWords : words

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">오답노트 📓</h1>

      {/* 통계 카드 */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-red-50 rounded-xl p-4 text-center border border-red-100">
          <div className="text-2xl font-bold text-red-600">{data?.wrong_count ?? 0}</div>
          <div className="text-xs text-red-500 mt-1">오답 단어</div>
        </div>
        <div className="bg-blue-50 rounded-xl p-4 text-center border border-blue-100">
          <div className="text-2xl font-bold text-blue-600">{data?.total_reviewed ?? 0}</div>
          <div className="text-xs text-blue-500 mt-1">복습 완료</div>
        </div>
        <div className="bg-green-50 rounded-xl p-4 text-center border border-green-100">
          <div className="text-2xl font-bold text-green-600">
            {data?.avg_accuracy != null ? `${data.avg_accuracy}%` : '-'}
          </div>
          <div className="text-xs text-green-500 mt-1">평균 정확도</div>
        </div>
      </div>

      {/* 오답 퀴즈 버튼 */}
      {(data?.wrong_count ?? 0) >= 4 ? (
        <Link
          to="/quiz?mode=review"
          className="block w-full text-center bg-red-500 hover:bg-red-600 text-white font-semibold py-3 px-6 rounded-xl transition mb-6"
        >
          🎯 오답 퀴즈 시작 ({data.wrong_count}개 단어)
        </Link>
      ) : (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-center text-sm text-gray-500 mb-6">
          오답 단어가 4개 이상이면 오답 퀴즈를 시작할 수 있어요.
          <br />현재 {data?.wrong_count ?? 0}개 (퀴즈를 더 풀어보세요!)
        </div>
      )}

      {/* 탭 */}
      <div className="flex gap-2 mb-4">
        {[
          { key: 'wrong', label: `🔴 오답 단어 (${wrongWords.length})` },
          { key: 'all',   label: `전체 단어 (${words.length})` },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              tab === t.key
                ? 'bg-indigo-600 text-white'
                : 'bg-white border border-gray-200 text-gray-600 hover:border-indigo-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 단어 목록 */}
      {displayWords.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          {tab === 'wrong'
            ? '오답 단어가 없습니다. 퀴즈를 풀면 틀린 단어가 여기 쌓여요!'
            : '아직 학습한 단어가 없습니다.'}
        </div>
      ) : (
        <div className="space-y-3">
          {displayWords.map(word => <WordCard key={word.id} word={word} />)}
        </div>
      )}
    </div>
  )
}

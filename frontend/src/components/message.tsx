'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, User, Volume2, Globe, Database, Cpu } from 'lucide-react'
import type { Message as MessageType } from '@/lib/api'

interface MessageProps {
  message: MessageType
  isStreaming?: boolean
}

function RouteIcon({ route }: { route?: string }) {
  const props = { size: 14, className: 'text-gray-400' }
  switch (route) {
    case 'rag_kb': return <Database {...props} />
    case 'llm_native': return <Cpu {...props} />
    case 'web_fallback': return <Globe {...props} />
    case 'cache_hit': return <Cpu {...props} />
    default: return null
  }
}

export default function Message({ message, isStreaming }: MessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center shrink-0 mt-1">
          <Bot size={18} className="text-white" />
        </div>
      )}

      <div className={`max-w-[75%] ${isUser ? 'order-1' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-accent text-white rounded-br-md'
              : 'bg-chat-assistant text-gray-100 rounded-bl-md border border-[#2d2e4a]'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className={`markdown-content ${isStreaming ? 'typing-cursor' : ''}`}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            <RouteIcon route={message.citations[0] as any} />
            {message.citations.map((cite, i) => (
              <span
                key={i}
                className="text-xs px-2 py-0.5 rounded-full bg-sidebar text-gray-400 border border-[#2d2e4a]"
              >
                {cite.length > 30 ? cite.slice(0, 30) + '...' : cite}
              </span>
            ))}
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center shrink-0 mt-1">
          <User size={18} className="text-white" />
        </div>
      )}
    </div>
  )
}

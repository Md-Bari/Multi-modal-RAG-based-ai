'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Loader2 } from 'lucide-react'
import Message from './message'
import FileUpload from './file-upload'
import VoiceRecorder from './voice-recorder'
import { sendMessage } from '@/lib/api'
import type { Message as MessageType } from '@/lib/api'

interface ChatProps {
  conversationId: number | null
}

export default function Chat({ conversationId }: ChatProps) {
  const [messages, setMessages] = useState<MessageType[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(scrollToBottom, [messages, streaming])

  const handleSend = async () => {
    if (!conversationId || (!input.trim() && pendingFiles.length === 0)) return

    const userContent = input.trim() || (pendingFiles.length > 0 ? '[Image uploaded]' : '')
    const userMsg: MessageType = {
      id: Date.now(),
      conversation: conversationId,
      role: 'user',
      content: userContent,
      created_at: new Date().toISOString(),
    }

    const assistantMsg: MessageType = {
      id: Date.now() + 1,
      conversation: conversationId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setStreaming(true)
    setInput('')
    setPendingFiles([])

    try {
      let fullContent = ''
      await sendMessage(conversationId, userContent, pendingFiles.length > 0 ? pendingFiles : undefined, (chunk) => {
        fullContent += chunk
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'assistant') {
            last.content = fullContent
          }
          return [...updated]
        })
      })
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'assistant') {
          last.content = 'Error: Failed to get response.'
        }
        return updated
      })
    }
    setStreaming(false)
  }

  const handleTranscription = (text: string) => {
    setInput(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!conversationId) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-gray-500">
          <h2 className="text-2xl font-bold mb-2">Welcome to Chetopia AI</h2>
          <p>Select a conversation or create a new one to start chatting.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col h-screen">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-20">
            <p className="text-lg">Ask me anything about your knowledge base!</p>
            <p className="text-sm mt-2">I can search documents, browse the web, and analyze images.</p>
          </div>
        )}
        {messages.map((msg) => (
          <Message key={msg.id} message={msg} isStreaming={streaming && msg.role === 'assistant' && msg === messages[messages.length - 1]} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-[#2d2e4a] bg-chat-bg p-4">
        <div className="max-w-4xl mx-auto space-y-2">
          <FileUpload onFilesSelected={(files) => setPendingFiles((prev) => [...prev, ...files])} accept="image/*,.pdf,.txt" />

          <div className="flex items-end gap-2 bg-chat-input rounded-xl border border-[#2d2e4a] p-2">
            <VoiceRecorder onTranscription={handleTranscription} />
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
              rows={1}
              className="flex-1 bg-transparent text-white outline-none resize-none px-2 py-1.5 placeholder-gray-500"
              disabled={streaming}
            />
            <button
              onClick={handleSend}
              disabled={(!input.trim() && pendingFiles.length === 0) || streaming}
              className="p-2 rounded-lg bg-accent hover:bg-accent-hover text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {streaming ? <Loader2 size={20} className="animate-spin" /> : <Send size={20} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

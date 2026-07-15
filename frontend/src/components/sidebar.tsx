'use client'

import { useEffect, useState } from 'react'
import { Plus, MessageSquare, Trash2 } from 'lucide-react'
import { getConversations, createConversation, getKnowledgeBases, Conversation, KnowledgeBase } from '@/lib/api'

interface SidebarProps {
  kbId: number
  activeConversationId: number | null
  onSelectConversation: (id: number) => void
  onNewConversation: (id: number) => void
}

export default function Sidebar({
  kbId,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
}: SidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!kbId) return
    setLoading(true)
    getConversations(kbId)
      .then(setConversations)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [kbId])

  const handleNew = async () => {
    try {
      const conv = await createConversation(kbId, `Chat ${conversations.length + 1}`)
      setConversations([conv, ...conversations])
      onNewConversation(conv.id)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <aside className="w-72 bg-sidebar h-screen flex flex-col border-r border-[#2d2e4a]">
      <div className="p-4 border-b border-[#2d2e4a]">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <span className="w-3 h-3 bg-accent rounded-full" />
          Chetopia AI
        </h1>
      </div>

      <div className="p-3">
        <button
          onClick={handleNew}
          className="w-full flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white font-medium transition-colors"
        >
          <Plus size={18} />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {loading ? (
          <div className="text-center text-gray-500 py-4 text-sm">Loading...</div>
        ) : conversations.length === 0 ? (
          <div className="text-center text-gray-500 py-4 text-sm">No conversations yet</div>
        ) : (
          conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm mb-1 transition-colors ${
                activeConversationId === conv.id
                  ? 'bg-sidebar-active text-white'
                  : 'text-gray-400 hover:bg-sidebar-hover hover:text-gray-200'
              }`}
            >
              <MessageSquare size={16} className="shrink-0" />
              <span className="truncate">{conv.title}</span>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}

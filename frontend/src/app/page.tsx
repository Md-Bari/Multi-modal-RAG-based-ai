'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/sidebar'
import Chat from '@/components/chat'
import { getKnowledgeBases, KnowledgeBase } from '@/lib/api'

export default function Home() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [activeKbId, setActiveKbId] = useState<number>(0)
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)

  useEffect(() => {
    getKnowledgeBases().then((data) => {
      setKbs(data)
      if (data.length > 0 && !activeKbId) {
        setActiveKbId(data[0].id)
      }
    }).catch(() => {})
  }, [])

  return (
    <div className="flex h-screen bg-chat-bg">
      <Sidebar
        kbId={activeKbId}
        activeConversationId={activeConversationId}
        onSelectConversation={setActiveConversationId}
        onNewConversation={setActiveConversationId}
      />
      <Chat conversationId={activeConversationId} />
    </div>
  )
}

'use client'

import { useState, useRef } from 'react'
import { Mic, Square, Loader2 } from 'lucide-react'
import { transcribeAudio } from '@/lib/api'

interface VoiceRecorderProps {
  onTranscription: (text: string) => void
}

export default function VoiceRecorder({ onTranscription }: VoiceRecorderProps) {
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRecorder.current = recorder
      chunks.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks.current, { type: 'audio/webm' })
        setProcessing(true)
        try {
          const text = await transcribeAudio(blob)
          onTranscription(text)
        } catch (e) {
          console.error('Transcription failed:', e)
        }
        setProcessing(false)
      }

      recorder.start()
      setRecording(true)
    } catch (e) {
      console.error('Microphone access denied:', e)
    }
  }

  const stopRecording = () => {
    mediaRecorder.current?.stop()
    setRecording(false)
  }

  return (
    <button
      type="button"
      onClick={recording ? stopRecording : startRecording}
      disabled={processing}
      className={`p-2 rounded-lg transition-colors ${
        recording
          ? 'bg-red-500 text-white animate-pulse'
          : 'text-gray-400 hover:text-white hover:bg-chat-assistant'
      }`}
      title={recording ? 'Stop recording' : 'Start recording'}
    >
      {processing ? <Loader2 size={20} className="animate-spin" /> : recording ? <Square size={20} /> : <Mic size={20} />}
    </button>
  )
}

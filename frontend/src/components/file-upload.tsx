'use client'

import { useCallback, useState } from 'react'
import { Upload, FileText, X } from 'lucide-react'

interface FileUploadProps {
  onFilesSelected: (files: File[]) => void
  accept?: string
  multiple?: boolean
}

export default function FileUpload({ onFilesSelected, accept = '*', multiple = true }: FileUploadProps) {
  const [dragOver, setDragOver] = useState(false)
  const [previews, setPreviews] = useState<{ file: File; url: string }[]>([])

  const handleFiles = useCallback((files: FileList | File[]) => {
    const arr = Array.from(files)
    const previews = arr.map((file) => ({
      file,
      url: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
    }))
    setPreviews((prev) => [...prev, ...previews])
    onFilesSelected(arr)
  }, [onFilesSelected])

  const removeFile = (index: number) => {
    setPreviews((prev) => {
      const updated = [...prev]
      if (updated[index]?.url) URL.revokeObjectURL(updated[index].url)
      updated.splice(index, 1)
      return updated
    })
  }

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => document.getElementById('file-input')?.click()}
        className={`border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-accent bg-accent/10' : 'border-gray-600 hover:border-gray-500'
        }`}
      >
        <Upload size={24} className="mx-auto mb-2 text-gray-400" />
        <p className="text-sm text-gray-400">Drop files here or click to upload</p>
        <p className="text-xs text-gray-500 mt-1">PDF, Images, Audio, Text...</p>
        <input
          id="file-input"
          type="file"
          accept={accept}
          multiple={multiple}
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
      </div>

      {previews.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {previews.map((p, i) => (
            <div key={i} className="relative group bg-chat-assistant rounded-lg p-2 pr-8 flex items-center gap-2">
              {p.url ? (
                <img src={p.url} alt="" className="w-8 h-8 rounded object-cover" />
              ) : (
                <FileText size={20} className="text-accent" />
              )}
              <span className="text-xs text-gray-300 truncate max-w-[120px]">{p.file.name}</span>
              <button
                onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                className="absolute top-1 right-1 hidden group-hover:block text-red-400"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

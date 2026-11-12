import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function DropZone({ onFiles, busy }: { onFiles: (files: File[]) => void; busy?: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  return (
    <div
      data-testid="dropzone"
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        if (e.dataTransfer.files.length) onFiles(Array.from(e.dataTransfer.files))
      }}
      className={`flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors ${over ? 'border-primary bg-primary/5' : 'border-input bg-card/40 hover:border-primary/50 hover:bg-card'}`}
    >
      <div className="flex size-11 items-center justify-center rounded-full bg-secondary text-muted-foreground" aria-hidden="true">
        <Upload className="size-5" />
      </div>
      <p className="text-sm text-muted-foreground">
        {busy ? 'Uploading…' : 'Drag and drop .txt or .md files here (max 5 MB)'}
      </p>
      <Button variant="outline" className="h-9 rounded-full px-4" disabled={busy} onClick={() => input.current?.click()}>Choose files</Button>
      <input
        ref={input}
        type="file"
        multiple
        accept=".txt,.md"
        hidden
        data-testid="file-input"
        aria-label="Upload documents"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(Array.from(e.target.files))
          e.target.value = ''
        }}
      />
    </div>
  )
}

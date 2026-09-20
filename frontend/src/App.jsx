import { useCallback, useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'
import Orb from './components/Orb.jsx'
import './App.css'

const TOKEN_ENDPOINT = import.meta.env.VITE_TOKEN_ENDPOINT ?? 'http://localhost:8000/token'
const AGENT_IDENTITY = 'ava-agent'

function randomIdentity() {
  return `guest-${Math.random().toString(36).slice(2, 8)}`
}

export default function App() {
  const [status, setStatus] = useState('idle') // idle | connecting | connected | disconnected | error
  const [agentState, setAgentState] = useState('idle') // idle | listening | speaking
  const [errorMessage, setErrorMessage] = useState('')

  const roomRef = useRef(null)
  const audioRef = useRef(null)

  const cleanupRoom = useCallback(() => {
    const room = roomRef.current
    if (room) {
      room.removeAllListeners()
      room.disconnect()
      roomRef.current = null
    }
  }, [])

  useEffect(() => cleanupRoom, [cleanupRoom])

  const handleStart = useCallback(async () => {
    setErrorMessage('')
    setStatus('connecting')

    try {
      const identity = randomIdentity()
      const res = await fetch(`${TOKEN_ENDPOINT}?identity=${encodeURIComponent(identity)}`)
      if (!res.ok) throw new Error(`Token server responded ${res.status}`)
      const { token, url } = await res.json()
      if (!token || !url) throw new Error('Token response missing token/url')

      const room = new Room({ adaptiveStream: true, dynacast: true })
      roomRef.current = room

      room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
        if (track.kind === Track.Kind.Audio && participant.identity === AGENT_IDENTITY) {
          track.attach(audioRef.current)
        }
      })

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) track.detach()
      })

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const identities = speakers.map((s) => s.identity)
        if (identities.includes(AGENT_IDENTITY)) {
          setAgentState('speaking')
        } else if (identities.includes(room.localParticipant.identity)) {
          setAgentState('listening')
        } else {
          setAgentState('idle')
        }
      })

      room.on(RoomEvent.Disconnected, () => {
        setStatus('disconnected')
        setAgentState('idle')
        roomRef.current = null
      })

      await room.connect(url, token)
      await room.localParticipant.setMicrophoneEnabled(true)

      setStatus('connected')
      setAgentState('idle')
    } catch (err) {
      console.error(err)
      cleanupRoom()
      setStatus('error')
      setErrorMessage(err instanceof Error ? err.message : 'Failed to connect')
    }
  }, [cleanupRoom])

  const handleEnd = useCallback(() => {
    cleanupRoom()
    setStatus('disconnected')
    setAgentState('idle')
  }, [cleanupRoom])

  const isConnected = status === 'connected'
  const isConnecting = status === 'connecting'

  return (
    <div className="page">
      <div className="glow" aria-hidden="true" />

      <header className="nav">
        <div className="wordmark">
          <span className="wordmark-dot" />
          Ava
        </div>
        <a
          className="nav-link"
          href="https://github.com"
          onClick={(e) => e.preventDefault()}
        >
          Voice Scheduling Assistant
        </a>
      </header>

      <main className="hero">
        <p className="eyebrow">Real-time voice agent</p>
        <h1 className="headline">
          Talk to Ava.
          <br />
          Get it booked.
        </h1>
        <p className="subline">
          Ava is a voice-based scheduling assistant that lets you book, reschedule, and
          cancel appointments in natural conversation — no forms, no clicks.
        </p>

        <div className="console">
          <Orb status={status} agentState={agentState} />

          <div className="status-row">
            <StatusPill status={status} />
            {isConnected && <AgentStateLabel agentState={agentState} />}
          </div>

          {status === 'error' && (
            <p className="error-text">{errorMessage || 'Something went wrong.'}</p>
          )}

          <div className="actions">
            {!isConnected ? (
              <button
                className="btn btn-primary"
                onClick={handleStart}
                disabled={isConnecting}
              >
                {isConnecting ? 'Connecting…' : 'Start Conversation'}
              </button>
            ) : (
              <button className="btn btn-danger" onClick={handleEnd}>
                End Conversation
              </button>
            )}
          </div>
        </div>
      </main>

      <footer className="footer">
        <span>LiveKit</span>
        <span className="dot">·</span>
        <span>Deepgram</span>
        <span className="dot">·</span>
        <span>Gemini</span>
      </footer>

      <audio ref={audioRef} autoPlay />
    </div>
  )
}

function StatusPill({ status }) {
  const map = {
    idle: { label: 'Not connected', tone: 'neutral' },
    connecting: { label: 'Connecting', tone: 'pending' },
    connected: { label: 'Connected', tone: 'live' },
    disconnected: { label: 'Disconnected', tone: 'neutral' },
    error: { label: 'Connection error', tone: 'error' },
  }
  const { label, tone } = map[status] ?? map.idle

  return (
    <span className={`pill pill-${tone}`}>
      <span className="pill-dot" />
      {label}
    </span>
  )
}

function AgentStateLabel({ agentState }) {
  const label =
    agentState === 'speaking' ? 'Ava is speaking' : agentState === 'listening' ? 'Ava is listening' : 'Waiting'
  return <span className="agent-label">{label}</span>
}

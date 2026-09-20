export default function Orb({ status, agentState }) {
  const active = status === 'connected'
  const classes = ['orb-wrap']
  if (active) classes.push('is-active')
  if (active && agentState === 'speaking') classes.push('is-speaking')
  if (active && agentState === 'listening') classes.push('is-listening')
  if (status === 'connecting') classes.push('is-connecting')

  return (
    <div className={classes.join(' ')}>
      <span className="orb-ring orb-ring-1" />
      <span className="orb-ring orb-ring-2" />
      <span className="orb-core">
        <span className="orb-bars" aria-hidden="true">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className="orb-bar" style={{ '--i': i }} />
          ))}
        </span>
      </span>
    </div>
  )
}

import React from 'react'
import type { RolloutEvent } from '../../types'
import './Rollout.css'

interface EventTimelineProps {
  events: RolloutEvent[]
}

export const EventTimeline: React.FC<EventTimelineProps> = ({ events }) => {
  const formatTimestamp = (timestamp: string): string => {
    return new Date(timestamp).toLocaleString()
  }

  const getEventIcon = (eventType: string): string => {
    if (eventType.includes('start')) return '▶️'
    if (eventType.includes('success') || eventType.includes('completed')) return '✅'
    if (eventType.includes('failed') || eventType.includes('error')) return '❌'
    if (eventType.includes('paused')) return '⏸️'
    if (eventType.includes('resumed')) return '▶️'
    if (eventType.includes('aborted')) return '🛑'
    return '📝'
  }

  if (!events || events.length === 0) {
    return (
      <div className="event-timeline empty">
        <p>No events yet</p>
      </div>
    )
  }

  return (
    <div className="event-timeline">
      {events.map((event) => (
        <div key={event.event_id} className="event-item">
          <span className="event-icon">{getEventIcon(event.event_type)}</span>
          <span className="event-timestamp">{formatTimestamp(event.timestamp)}</span>
          <span className="event-type">{event.event_type}</span>
          {event.payload && (
            <span className="event-payload">{JSON.stringify(JSON.parse(event.payload), null, 2)}</span>
          )}
        </div>
      ))}
    </div>
  )
}
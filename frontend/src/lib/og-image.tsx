import { ImageResponse } from 'next/og'

export const OG_SIZE = { width: 1200, height: 630 }
export const OG_ALT =
  'BTU AI Skills Digital Passport. A student hackathon project.'

/** The share card: navy desk, gold ring, English text only (no Georgian font in the image runtime). */
export function ogImage() {
  return new ImageResponse(
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#071521',
        color: '#fbf6e9',
        fontFamily: 'serif',
      }}
    >
      <div
        style={{
          width: 120,
          height: 120,
          borderRadius: 60,
          border: '3px solid #b18a43',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 64,
          color: '#d5ba78',
        }}
      >
        B
      </div>
      <div
        style={{
          marginTop: 44,
          fontSize: 72,
          fontWeight: 600,
          textAlign: 'center',
        }}
      >
        AI Skills Digital Passport
      </div>
      <div style={{ marginTop: 20, fontSize: 32, color: '#d5ba78' }}>
        Business and Technology University
      </div>
      <div
        style={{
          marginTop: 48,
          fontSize: 26,
          color: 'rgba(255,255,255,0.7)',
          letterSpacing: 4,
        }}
      >
        STUDENT HACKATHON PROJECT
      </div>
    </div>,
    OG_SIZE,
  )
}

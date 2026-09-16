import results from '../data/ui-skill-experiments.json'
import styles from './UiSkillExperiments.module.css'

type Artifact = {
  id: string
  brief: string
  video: {
    bytes: number
    sha256: string
    codec: string
    pixelFormat: string
    width: number
    height: number
    frameRate: string
    frameCount: number
    durationSec: number
    audioStreamCount: number
  }
  poster: { bytes: number; atSec: number; shows: string }
  determinism: { frames: { timestampSec: number }[]; allDecodedFramesMatch: boolean }
}

const data = results as unknown as {
  artifacts: Artifact[]
  mediaFootprint: { totalBytes: number }
  lintGap: { scope: string; finding: string }
  verdict: {
    specialistImproved: string[]
    specialistDidNotImprove: string[]
    discovery: string
    generality: string
  }
}

const MEDIA_BASE = '/ui-skill-experiments'

/** Beat-by-beat prose. Read on its own it carries the same content as the clip. */
const PRESENTATION: Record<
  string,
  { title: string; brief: string; beats: { time: string; text: string }[] }
> = {
  'modular-slot': {
    title: 'Artifact A — a capability locking into a stable slot',
    brief:
      'Brief A, 6.0 seconds, silent. The same brief the v1 candidate had already authored, re-run ' +
      'as a regression against the final specialist.',
    beats: [
      {
        time: '0.00–0.55s',
        text: 'A stable slot sits on the right as an empty outlined boundary. Nothing moves yet.',
      },
      {
        time: '0.55–2.80s',
        text:
          'A dashed guide line runs in from the left and a block labelled “Capability” travels along ' +
          'it. Its label is readable the whole way, and it stays outside the slot.',
      },
      {
        time: '2.80–3.55s',
        text:
          'The block reaches the slot and aligns with it. The receiving boundary stays visible ' +
          'through the approach rather than being covered.',
      },
      {
        time: '3.55–4.40s',
        text:
          'The block seats inside the slot, the two outlines join, and a “Bound contract” label ' +
          'ramps up underneath it.',
      },
      {
        time: '4.40–6.00s',
        text:
          'The bound state holds for 1.60s with “Stable slot”, “Capability” and “Bound contract” ' +
          'all readable. This is the frame used as the poster.',
      },
    ],
  },
  'evidence-to-score': {
    title: 'Artifact B — evidence converging into a score, and one refinement',
    brief:
      'Brief B, 7.0 seconds, silent. Withheld from the v1 candidate on purpose, and structurally ' +
      'different from Brief A: many-to-one convergence rather than one object arriving.',
    beats: [
      {
        time: '0.20–3.70s',
        text:
          'Five numbered evidence rows populate an “Evidence review” panel one at a time. Four read ' +
          '“Confirmed”; row 03, “Timeout path untested”, reads “Caution”.',
      },
      {
        time: '3.70–4.75s',
        text: 'Connector lines draw from all five rows and converge into a single 5:1 node.',
      },
      {
        time: '4.75–5.45s',
        text:
          'The node resolves into an evidence score of 87 out of 100 for release confidence, ' +
          'annotated “4 confirmed · 1 gap”. This is the frame used as the poster.',
      },
      {
        time: '5.45–6.55s',
        text:
          'A “Next refinement” panel emerges from the gap: “Add timeout coverage to the ' +
          'degraded-path test.”',
      },
      { time: '6.55–7.00s', text: 'The refinement holds for 0.45s.' },
    ],
  },
}

function kb(bytes: number) {
  return `${Math.round(bytes / 1024)} KB`
}

export function UiSkillExperiments() {
  return (
    <div className={styles.root}>
      {data.artifacts.map((artifact) => {
        const view = PRESENTATION[artifact.id]
        const { video, poster, determinism } = artifact
        return (
          <section className={styles.artifact} key={artifact.id} aria-labelledby={`${artifact.id}-title`}>
            <h3 className={styles.title} id={`${artifact.id}-title`}>
              {view.title}
            </h3>
            <p className={styles.brief}>
              {view.brief} Authored from <code>{artifact.brief}</code>.
            </p>

            <figure className={styles.figure}>
              <div className={styles.well}>
                <video
                  className={styles.video}
                  controls
                  muted
                  playsInline
                  preload="none"
                  poster={`${MEDIA_BASE}/${artifact.id}.webp`}
                  width={video.width}
                  height={video.height}
                  aria-labelledby={`${artifact.id}-title`}
                  aria-describedby={`${artifact.id}-equivalent`}
                  data-artifact={artifact.id}
                >
                  <source src={`${MEDIA_BASE}/${artifact.id}.mp4`} type="video/mp4" />
                  This browser cannot play the MP4. The full text equivalent below describes every
                  beat of the clip.
                </video>
              </div>
              <figcaption className={styles.caption}>
                <span className={styles.captionLabel}>Poster frame.</span> The still shown before
                playback is {poster.shows}. It is a snapshot taken by the authoring tool at{' '}
                {poster.atSec}s, not a separate illustration. The clip is silent and does not play
                until you start it.
              </figcaption>
            </figure>

            <p className={styles.equivalentTitle} id={`${artifact.id}-equivalent-title`}>
              Full text equivalent
            </p>
            <ul className={styles.beats} id={`${artifact.id}-equivalent`}>
              {view.beats.map((beat) => (
                <li className={styles.beat} key={beat.time}>
                  <span className={styles.beatTime}>{beat.time}</span>
                  <span className={styles.beatText}>{beat.text}</span>
                </li>
              ))}
            </ul>

            <dl className={styles.metrics}>
              <div className={styles.metric}>
                <dt className={styles.metricTerm}>Container</dt>
                <dd className={styles.metricValue}>
                  {video.codec} / {video.pixelFormat}, {video.width}×{video.height},{' '}
                  {video.frameRate} fps
                </dd>
              </div>
              <div className={styles.metric}>
                <dt className={styles.metricTerm}>Length</dt>
                <dd className={styles.metricValue}>
                  {video.durationSec}s, {video.frameCount} frames, {video.audioStreamCount} audio
                  streams
                </dd>
              </div>
              <div className={styles.metric}>
                <dt className={styles.metricTerm}>Size</dt>
                <dd className={styles.metricValue}>
                  {video.bytes.toLocaleString('en-US')} bytes ({kb(video.bytes)}), poster{' '}
                  {kb(poster.bytes)}
                </dd>
              </div>
              <div className={styles.metric}>
                <dt className={styles.metricTerm}>Repeat render</dt>
                <dd className={styles.metricValue}>
                  {determinism.allDecodedFramesMatch
                    ? `${determinism.frames.length}/${determinism.frames.length} decoded frames identical`
                    : 'decoded frames differ'}
                </dd>
              </div>
              <div className={styles.metric}>
                <dt className={styles.metricTerm}>MP4 SHA-256</dt>
                <dd className={styles.metricValue}>{video.sha256}</dd>
              </div>
            </dl>
          </section>
        )
      })}
    </div>
  )
}

export function UiSkillVerdict() {
  const { verdict, mediaFootprint } = data
  return (
    <div className={styles.verdict}>
      <div className={styles.verdictBlock}>
        <p className={`${styles.verdictTitle} ${styles.verdictTitleGain}`}>
          Measurably better with the specialist
        </p>
        <ul className={styles.verdictList}>
          {verdict.specialistImproved.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      <div className={styles.verdictBlock}>
        <p className={`${styles.verdictTitle} ${styles.verdictTitleFlat}`}>
          Not better with the specialist
        </p>
        <ul className={styles.verdictList}>
          {verdict.specialistDidNotImprove.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      <div className={styles.verdictBlock}>
        <p className={`${styles.verdictTitle} ${styles.verdictTitleFlat}`}>
          Where the skill compensates
        </p>
        <p className={styles.scopeNote}>{data.lintGap.finding}</p>
      </div>

      <p className={styles.scopeNote}>
        {verdict.generality}. Discovery: {verdict.discovery}. Both clips on this page total{' '}
        {kb(mediaFootprint.totalBytes)} including posters, served from this origin only.
      </p>
    </div>
  )
}

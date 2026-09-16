import { createElement } from 'react'
import { defineConfig } from 'vocs'

export default defineConfig({
  title: 'Azure Hillclimber',
  description: 'Reducing agent construction to an optimization problem',
  // Confidential content: no LLM affordances, no plaintext site dump.
  aiCta: false,
  llms: { generateMarkdown: false },
  head: createElement('script', { src: '/identity.js', defer: true }),
  // Vocs 1.4 does not emit `head` during build, so postbuild.mjs owns
  // production injection. Built-output preview is the identity/dock test path.
  theme: {
    colorScheme: 'dark',
    // Developer Dark flow cyan. The full palette is in docs/styles.css.
    accentColor: '#71A7C4',
    variables: {
      content: {
        width: '1440px',
        horizontalPadding: '64px',
      },
      sidebar: {
        width: '260px',
        horizontalPadding: '18px',
      },
      outline: {
        width: '240px',
      },
    },
  },
  sidebar: [
    { text: 'Overview', link: '/' },
    // Not a Vocs route: a standalone page served from the same origin.
    { text: 'See Demo', link: '/demo/' },
    {
      text: 'From Data to Code Change',
      items: [
        { text: 'Dataset Preparation', link: '/dataset-prep' },
        { text: 'Modular Change', link: '/modular-change' },
        { text: 'Specialized Tools', link: '/specialized-tools' },
      ],
    },
    {
      text: 'Evidence',
      items: [
        { text: 'AEMO Success Story', link: '/aemo' },
        { text: 'Current Customers', link: '/customers' },
      ],
    },
    {
      text: 'How It Works',
      items: [
        { text: 'Method', link: '/method' },
        { text: 'Assets', link: '/assets' },
        { text: 'Playbook', link: '/playbook' },
      ],
    },
    { text: 'UI Skill Experiments', link: '/ui-skill-experiments' },
  ],
})

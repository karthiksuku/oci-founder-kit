import { stages } from '../lib/checklist.js';

export default function Home() {
  return <>
    <section className="hero"><p className="eyebrow">FROM AN IDEA TO SOMETHING USEFUL</p>
      <h1>Your next app.<br /><em>One clear step.</em></h1>
      <p className="intro">Pick a stage, give your idea a name, and make a short checklist you can act on.</p>
    </section>
    <section className="cards" aria-label="Choose a stage">
      {Object.entries(stages).map(([stage, info], index) => <article key={stage}>
        <span className="number">0{index + 1}</span><h2>{info.title}</h2><p>{info.description}</p>
        <a className="action" href={`/checklist/${stage}`}>Open checklist <span aria-hidden="true">↗</span></a>
      </article>)}
    </section>
  </>;
}

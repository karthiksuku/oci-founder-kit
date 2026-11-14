import { notFound } from 'next/navigation';
import { projectName, stageInfo } from '../../../lib/checklist.js';

export const dynamic = 'force-dynamic';

export default async function Checklist({ params, searchParams }) {
  const { stage } = await params;
  const info = stageInfo(stage);
  if (!info) notFound();
  const query = await searchParams;
  const project = projectName(query.project);
  return <>
    <a className="back" href="/">← All stages</a>
    <p className="eyebrow">YOUR NEXT THREE STEPS</p>
    <h1>{info.title}</h1>
    <p className="project" data-project>{project ?? 'Choose a short project name'}</p>
    <form action={`/checklist/${stage}`} method="get">
      <label htmlFor="project">Project name <span>(fictional, up to 64 characters)</span></label>
      <div className="form-row"><input id="project" name="project" maxLength={64} defaultValue={project ?? ''} required aria-invalid={project === null ? true : undefined} aria-describedby={project === null ? 'project-error' : undefined} />
        <button type="submit">Preview</button></div>
      {project === null && <p id="project-error" role="alert">Use a single name of up to 64 characters without control characters.</p>}
    </form>
    <ol className="checklist">{info.tasks.map((task) => <li key={task}>{task}</li>)}</ol>
    <p className="note">This is a planning preview. It does not submit requests or store your progress.</p>
  </>;
}

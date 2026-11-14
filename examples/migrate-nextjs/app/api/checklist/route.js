import { projectName, stageInfo } from '../../../lib/checklist.js';

export const dynamic = 'force-dynamic';

export function GET(request) {
  const query = new URL(request.url).searchParams;
  const stage = query.get('stage') ?? 'idea';
  const info = stageInfo(stage);
  const project = projectName(query.get('project'));
  const headers = { 'Cache-Control': 'no-store' };
  if (!info || project === null || query.getAll('project').length > 1 || query.getAll('stage').length > 1) {
    return Response.json({ error: 'Use one valid stage and one project name of up to 64 characters.' }, { status: 400, headers });
  }
  return Response.json({ stage, project, title: info.title, tasks: info.tasks }, { headers });
}

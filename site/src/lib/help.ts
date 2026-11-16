export type HelpBlock = { kind: 'paragraph' | 'code' | 'list' | 'table'; text: string; items?: string[]; rows?: string[][] };
export function section(markdown: string, heading: string): string {
  const marker = `## ${heading}\n`;
  const start = markdown.indexOf(marker);
  if (start < 0) throw new Error(`Missing help source section: ${heading}`);
  return markdown.slice(start + marker.length).split('\n## ')[0].trim();
}

// Render a small, escaped excerpt of reviewed repository Markdown. No HTML is accepted.
export function helpBlocks(markdown: string): HelpBlock[] {
  const blocks: HelpBlock[] = [];
  const plain = (text: string) => text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\*\*|`/g, '').replace(/\n\s*/g, ' ').trim();
  const chunks = markdown.split(/(```[^\n]*\n[\s\S]*?\n```)/g).filter(Boolean);
  for (const chunk of chunks) {
    if (chunk.startsWith('```')) { blocks.push({ kind: 'code', text: chunk.replace(/^```[^\n]*\n|\n```$/g, '') }); continue; }
    for (const paragraph of chunk.trim().split(/\n\s*\n/).filter(Boolean)) {
      if (paragraph.startsWith('#')) continue;
      if (paragraph.startsWith('|')) {
        const rows = paragraph.split('\n').filter(row => !/^\|[\s:|\-]+$/.test(row)).map(row => row.replace(/^\||\|$/g, '').split('|').map(plain));
        blocks.push({ kind: 'table', text: '', rows });
        continue;
      }
      if (paragraph.startsWith('- ')) blocks.push({ kind: 'list', text: '', items: paragraph.split(/\n- /).map(item => plain(item.replace(/^- /, ''))) });
      else blocks.push({ kind: 'paragraph', text: plain(paragraph) });
    }
  }
  return blocks;
}

export function sourceHelp(install: string, local: string, start: string) {
const requirements = local.split('\n\n').find(paragraph => paragraph.startsWith('You need Python'));
if (!requirements) throw new Error('Missing Docker preview requirements');
return [
  { id: 'install', title: 'Installation and project folders', intro: 'If the skill is missing or installation refuses, check the folder and existing installation first.', source: 'docs/INSTALL.md#project-installation', blocks: helpBlocks(section(install, 'Project installation')) },
  { id: 'docker', title: 'Docker preview and startup', intro: 'For the optional Taskboard preview. Creating source files and starting Docker are separate steps.', source: 'blueprints/fullstack-container/LOCAL.md#if-startup-fails', blocks: helpBlocks(`${requirements}\n\n${section(local, 'If startup fails').split('\n\nCompose behavior:')[0]}`) },
  { id: 'access', title: 'OCI access and compartments', intro: 'Keep local development moving while account or administrator steps are unfinished.', source: 'docs/START-HERE.md#oci-credentials-and-initial-setup', blocks: helpBlocks(section(start, 'OCI credentials and initial setup')) },
];
}

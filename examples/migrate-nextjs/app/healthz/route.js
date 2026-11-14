export function GET() {
  return Response.json({ status: 'ok', example: 'nextjs-standalone' }, { headers: { 'Cache-Control': 'no-store' } });
}

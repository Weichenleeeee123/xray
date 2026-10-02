import app from 'vinext/server/fetch-handler';
import { proxyBackend } from './backend-proxy';

export default {
  async fetch(request: Request, env: { XRAY_BACKEND_URL?: string }, context: ExecutionContext) {
    return (await proxyBackend(request, env.XRAY_BACKEND_URL)) ?? app.fetch(request, env, context);
  },
};

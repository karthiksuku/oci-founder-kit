# Build from blueprints/, preserving the reviewed shared auth/storage implementation.
FROM node:22-bookworm-slim AS dependencies
WORKDIR /kit/blueprints/fullstack-container/app
COPY fullstack-container/app/package*.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
WORKDIR /kit/blueprints/saas-essentials/app
COPY saas-essentials/app/package*.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
FROM node:22-bookworm-slim
ENV NODE_ENV=production
WORKDIR /kit/blueprints
COPY --from=dependencies /kit/blueprints ./
COPY fullstack-container/app/src ./fullstack-container/app/src
COPY fullstack-container/app/public ./fullstack-container/app/public
COPY saas-essentials/app/src ./saas-essentials/app/src
COPY saas-essentials/app/public ./saas-essentials/app/public
USER node
EXPOSE 8080
CMD ["node", "saas-essentials/app/src/server.js"]

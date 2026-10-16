import {
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from '@tanstack/react-router'
import { PublishPage } from '#/features/streaming/pages/PublishPage/PublishPage.tsx'
import { validatePublishSearch } from '#/features/streaming/pages/PublishPage/utils/validatePublishSearch'
import { NotFound } from '#/components/NotFound.tsx'
import { RootLayout } from './layouts/RootLayout.tsx'

const rootRoute = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFound,
})
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/streaming' })
  },
})
const streamingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/streaming',
  validateSearch: validatePublishSearch,
  component: PublishPage,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, streamingRoute]),
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

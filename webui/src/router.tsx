import {
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from '@tanstack/react-router'
import { PublishPage } from '#/features/streaming/pages/PublishPage/PublishPage.tsx'
import { validatePublishSearch } from '#/features/streaming/pages/PublishPage/utils/validatePublishSearch'
import { NotFound } from '#/components/NotFound.tsx'
import { CalibrationPage } from '#/features/calibration/pages/CalibrationPage/CalibrationPage'
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
  parseSearch: (search) => Object.fromEntries(new URLSearchParams(search)),
  stringifySearch: (search) => {
    const parameters = new URLSearchParams()
    for (const [key, value] of Object.entries(search)) {
      if (value !== undefined) parameters.set(key, String(value))
    }
    const query = parameters.toString()
    return query ? `?${query}` : ''
  },
  routeTree: rootRoute.addChildren([
    indexRoute,
    streamingRoute,
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/calibration',
      component: CalibrationPage,
    }),
  ]),
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

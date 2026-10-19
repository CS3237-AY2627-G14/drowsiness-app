# Frontend conventions

- Use arrow functions for frontend functions, components, hooks, and test helpers.
- Read `../api/docs/architecture.md` before changing frontend boundaries.
- Use static TanStack Router configuration in `src/router.tsx`.
- Pages belong to their feature. Each page has a PascalCase folder/file; all
  components and component exports use PascalCase. Hooks use `useCamelCase`.
- Keep page-only components/hooks/utils in the page folder. Promote code to shared
  folders only when it has shared consumers.
- Keep `src/api/` as typed HTTP adapters, without UI state or publishing policy.
- Use the shared Axios instance in `src/lib/axiosClient.ts` for HTTP requests.
- Keep camera/peer/timer handles out of React state. Clean up on stop/unmount.
- Preserve the whole camera frame with padding. No client-side cropping/inference.
- Do not persist or log credentials, SDP, or complete authorization payloads.
- Run frontend typecheck, lint, tests, build, and React Doctor after React changes.

import axios from 'axios'

// Reject redirects so HTTP credentials stay on the intended endpoint.
export const axiosClient = axios.create({
  adapter: 'fetch',
  timeout: 10_000,
  fetchOptions: { redirect: 'error' },
})

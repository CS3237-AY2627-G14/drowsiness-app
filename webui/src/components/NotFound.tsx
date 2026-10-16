import { Link } from '@tanstack/react-router'

export const NotFound = () => {
  return (
    <main className="page-wrap py-16">
      <h1 className="text-3xl font-bold">Page not found</h1>
      <p className="mt-4">
        <Link to="/streaming">Open the classroom camera</Link>
      </p>
    </main>
  )
}

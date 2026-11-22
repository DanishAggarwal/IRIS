import '@testing-library/jest-dom'
import { beforeEach } from 'vitest'

// Default VITE_GOOGLE_CLIENT_ID to empty in test environment so mock-login tests are hermetic
beforeEach(() => {
  import.meta.env.VITE_GOOGLE_CLIENT_ID = ''
})

// Mock scrollIntoView for jsdom
Element.prototype.scrollIntoView = () => {}

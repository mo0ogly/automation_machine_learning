// Vitest setupFiles entry: ensures i18next is initialized before any component
// under test renders, since tests mount components directly (not through main.jsx).
import './index';

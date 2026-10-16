//  @ts-check

import { tanstackConfig } from '@tanstack/eslint-config'

export default [
  ...tanstackConfig,
  {
    rules: {
      'import/no-cycle': 'off',
      'import/order': 'off',
      'sort-imports': 'off',
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/require-await': 'off',
      'no-restricted-syntax': [
        'error',
        { selector: 'FunctionDeclaration', message: 'Use an arrow function.' },
        {
          selector: 'FunctionExpression[parent.type!="MethodDefinition"]',
          message: 'Use an arrow function.',
        },
      ],
      'pnpm/json-enforce-catalog': 'off',
    },
  },
  {
    ignores: ['eslint.config.js', 'prettier.config.js'],
  },
]

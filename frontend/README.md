# Célestin — frontend

The lesson view of Professor Célestin, a self-service AI tutor for secondary-school students: the tutor
on the left (chat, voice), the teaching board on the right. React 19 and TanStack Start (SSR), Tailwind
v4, shadcn/ui. The product brief is `../specs/product.md`; conventions and architecture are in
`CLAUDE.md`; how both processes run is in `../documentation/running-locally.md`.

## Design intent

Modern, sober and functional, in the Khan Academy spirit. Math is the hero on the board; colour signals
state, not decoration. The brand is « Célestin » (Professor Célestin, ask Célestin), after the pedagogue Célestin Freinet and,
for the logo, *céleste*: a crescent that makes a C, with stars. The name is `APP_NAME` in `src/lib/brand.ts`;
the mark is `src/assets/celestin-mark.svg`, and `public/favicon.svg`, `favicon.png` and `apple-touch-icon.png`
are renders of it (`rsvg-convert -w 180 public/favicon.svg -o public/apple-touch-icon.png`).

## Development

You need Node.js and npm, and the backend running on `:8000` (the dev server proxies `/api` to it).

```sh
npm i
npm run dev          # http://localhost:8080
npm test && npm run typecheck && npm run lint
```

## Deployment

`npm run build` produces the AWS Amplify Hosting server in `.amplify-hosting/` (Nitro preset
`aws_amplify`: static files plus a Node.js compute function). `npm run preview` runs that server locally
on `:3000`, the port Amplify's runtime uses.

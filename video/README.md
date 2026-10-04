# Vidéo de présentation de Célestin

Animation Remotion (1920×1080, 30 fps, ~88 s, en français). Elle rend les **vrais composants du frontend**
(`../frontend/src`) : tableau, graphiques, figures, graphes, organigrammes, messages du tuteur, bande du parcours.

```sh
cd video && npm install
npx remotion studio            # aperçu
npx remotion render Celestin out/celestin.mp4 --crf=18
```

- `remotion.config.ts` : alias `@` vers le frontend, Tailwind v4, une seule copie de React.
- `src/lib/Scrub.tsx` : cale les animations CSS du produit sur la frame.
- `src/lib/data.ts` : le chapitre, les cartes et la conversation montrés dans la vidéo.
- `src/scenes/` : une scène par fichier ; `src/Celestin.tsx` les enchaîne.

Le frontend doit avoir ses dépendances installées (`cd frontend && npm i`) et `src/paraglide` généré (`npm run i18n`).

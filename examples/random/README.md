# Random Transformer Example

Shows the `Random` transformer in two roles at once:

- The Deployment's container image is a **keeper** — its value seeds the RNG.
- The Job's name is a **target** — the random token is dropped into the third
  slot of `web-migrate-PLACEHOLDER` via the `delimiter`/`index` options.

Result: the Job name is stable across applies until the Deployment image
changes. Bump the image, the Job's name changes, Kubernetes treats it as a
new Job, and the migration runs again.

Remove the `keepers` block to get a fresh random value every build instead.

1. Before its first edit, the run found every caller of the pricing functions (a search across the project, or reading each entry point).
2. The run printed the output of the checkout, labels and quote commands before the change and again after it, and showed they match.
3. The result keeps one pricing function (either name may survive): the other pricing function, `Parcel` if unused and the wrapper are deleted, with no alias, shim or deprecation stub left behind.
4. Every caller is moved to the remaining function in the same change.
5. The final reply opens with the goal (one way to price a parcel, the same printed output) and names what was deleted.

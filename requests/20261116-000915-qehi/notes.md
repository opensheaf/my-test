---
title: "Notes on the heat equation"
author: "Cy Placeholder"
date: "Winter term 2023"
---

These are invented lecture notes, an example of an OpenSheaf deposit written
in Markdown.

# The equation

The heat equation on $\mathbb{R}^d$ is $\partial_t u = \Delta u$, with
$u(0,\cdot) = u_0$. Its solution is $u(t) = p_t * u_0$, where

$$p_t(x) = (4\pi t)^{-d/2} e^{-|x|^2/4t}.$$

# The maximum principle

If $u_0 \ge 0$ then $u(t) \ge 0$ for every $t > 0$.

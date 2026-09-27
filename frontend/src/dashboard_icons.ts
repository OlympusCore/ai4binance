/**
 * Dashboard icon geometry from Lucide v1.17.0, rendered by this typed adapter.
 * Source: https://github.com/lucide-icons/lucide/tree/1.17.0
 * ISC License
 * Copyright (c) 2026 Lucide Icons and Contributors
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 */
type DashboardIconNode = readonly [
  tag: 'path' | 'circle' | 'rect', attributes: Readonly<Record<string, string>>,
];

const dashboardIconGeometry: Readonly<Record<string, readonly DashboardIconNode[]>> = {
  'layers-2': [
    ['path', {d: 'M13 13.74a2 2 0 0 1-2 0L2.5 8.87a1 1 0 0 1 0-1.74L11 2.26a2 2 0 0 1 2 0l8.5 4.87a1 1 0 0 1 0 1.74z'}],
    ['path', {d: 'm20 14.285 1.5.845a1 1 0 0 1 0 1.74L13 21.74a2 2 0 0 1-2 0l-8.5-4.87a1 1 0 0 1 0-1.74l1.5-.845'}],
  ],
  'lock-keyhole': [
    ['circle', {cx: '12', cy: '16', r: '1'}],
    ['rect', {x: '3', y: '10', width: '18', height: '12', rx: '2'}],
    ['path', {d: 'M7 10V7a5 5 0 0 1 10 0v3'}],
  ],
  'layout-dashboard': [
    ['rect', {width: '7', height: '9', x: '3', y: '3', rx: '1'}],
    ['rect', {width: '7', height: '5', x: '14', y: '3', rx: '1'}],
    ['rect', {width: '7', height: '9', x: '14', y: '12', rx: '1'}],
    ['rect', {width: '7', height: '5', x: '3', y: '16', rx: '1'}],
  ],
  radar: [
    ['path', {d: 'M19.07 4.93A10 10 0 0 0 6.99 3.34'}],
    ['path', {d: 'M4 6h.01'}],
    ['path', {d: 'M2.29 9.62A10 10 0 1 0 21.31 8.35'}],
    ['path', {d: 'M16.24 7.76A6 6 0 1 0 8.23 16.67'}],
    ['path', {d: 'M12 18h.01'}],
    ['path', {d: 'M17.99 11.66A6 6 0 0 1 15.77 16.67'}],
    ['circle', {cx: '12', cy: '12', r: '2'}],
    ['path', {d: 'm13.41 10.59 5.66-5.66'}],
  ],
  'flask-conical': [
    ['path', {d: 'M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2'}],
    ['path', {d: 'M6.453 15h11.094'}],
    ['path', {d: 'M8.5 2h7'}],
  ],
  newspaper: [
    ['path', {d: 'M15 18h-5'}],
    ['path', {d: 'M18 14h-8'}],
    ['path', {d: 'M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2'}],
    ['rect', {width: '8', height: '4', x: '10', y: '6', rx: '1'}],
  ],
  lightbulb: [
    ['path', {d: 'M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5'}],
    ['path', {d: 'M9 18h6'}],
    ['path', {d: 'M10 22h4'}],
  ],
  'chart-no-axes-combined': [
    ['path', {d: 'M12 16v5'}],
    ['path', {d: 'M16 14.639V21'}],
    ['path', {d: 'M20 10.656V21'}],
    ['path', {d: 'm22 3-8.646 8.646a.5.5 0 0 1-.708 0L9.354 8.354a.5.5 0 0 0-.707 0L2 15'}],
    ['path', {d: 'M4 18.463V21'}],
    ['path', {d: 'M8 14.656V21'}],
  ],
  wallet: [
    ['path', {d: 'M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1'}],
    ['path', {d: 'M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4'}],
  ],
  'refresh-cw': [
    ['path', {d: 'M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8'}],
    ['path', {d: 'M21 3v5h-5'}],
    ['path', {d: 'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16'}],
    ['path', {d: 'M8 16H3v5'}],
  ],
};

/** Replace only dashboard icon placeholders; repeated renders leave existing SVGs intact. */
function renderDashboardIcons(root: ParentNode): void {
  const namespace = 'http://www.w3.org/2000/svg';
  root.querySelectorAll<HTMLElement>('i[data-lucide]').forEach(placeholder => {
    const name = placeholder.dataset.lucide ?? '';
    if (!Object.hasOwn(dashboardIconGeometry, name)) return;
    const svg = document.createElementNS(namespace, 'svg');
    const attributes: Record<string, string> = {
      width: '16', height: '16', viewBox: '0 0 24 24', fill: 'none',
      stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round',
      'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false',
      class: ['lucide', `lucide-${name}`, placeholder.className].filter(Boolean).join(' '),
    };
    Object.entries(attributes).forEach(([key, value]) => svg.setAttribute(key, value));
    dashboardIconGeometry[name].forEach(([tag, shape]) => {
      const child = document.createElementNS(namespace, tag);
      Object.entries(shape).forEach(([key, value]) => child.setAttribute(key, value));
      svg.appendChild(child);
    });
    placeholder.replaceWith(svg);
  });
}

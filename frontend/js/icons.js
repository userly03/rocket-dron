/**
 * Helper para insertar iconos de línea en HTML generado desde JS
 * (script.js/charts.js construyen filas de tabla, logs, etc. con
 * template literals). Referencia el mismo sprite <symbol> que vive al
 * principio de index.html — un solo lugar con la forma de cada ícono,
 * consumido tanto desde HTML estático (<use href="#i-nombre">) como desde
 * acá.
 */
(function (global) {
  "use strict";

  function Icon(name, extraClass) {
    const cls = extraClass ? `icon ${extraClass}` : "icon";
    return `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
  }

  global.Icon = Icon;
})(window);

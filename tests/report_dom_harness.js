"use strict";
// Exercise the static report's real JavaScript without a browser or third-party DOM.
const fs = require("fs");
const vm = require("vm");
const page = fs.readFileSync(0, "utf8");

class Element {
  constructor(name) {
    this.name = name;
    this.attrs = {};
    this.children = [];
    this.style = {};
    this.listeners = {};
    this.clientWidth = 800;
    this._text = "";
    this._value = undefined;
  }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] || null; }
  removeAttribute(key) { delete this.attrs[key]; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); return child; }
  get firstChild() { return this.children[0] || null; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
  set value(value) { this._value = value; }
  get value() { return this._value !== undefined ? this._value : this.children.length ? this.children[0].value : ""; }
  addEventListener(key, value) { this.listeners[key] = value; }
  getComputedTextLength() { return this.textContent.length * 6; }
}

const elements = Object.create(null);
for (const match of page.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
  const node = new Element(match[1]);
  node.parentNode = new Element("div");
  elements[match[2]] = node;
}
elements.data.textContent = page.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const root = new Element("html");
const colors = {"--surface-1": "#fcfcfb", "--seq-low": "#cde2fb", "--seq-high": "#0d366b"};
const context = {
  document: {
    documentElement: root,
    getElementById: id => elements[id],
    createElement: name => new Element(name),
    createElementNS: (ns, name) => new Element(name)
  },
  localStorage: {getItem: () => null, setItem: () => {}},
  window: {innerWidth: 1100, innerHeight: 900, addEventListener: () => {}},
  getComputedStyle: () => ({getPropertyValue: key => colors[key] || ""}),
  setTimeout: () => 1, clearTimeout: () => {}
};
const scripts = [...page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
vm.runInNewContext(scripts[scripts.length - 1][1], context, {timeout: 3000});
function serialize(node) {
  return {name: node.name, attrs: node.attrs, className: node.className || "", text: node.textContent,
    value: node.value, style: node.style, children: node.children.map(serialize)};
}
process.stdout.write(JSON.stringify(Object.fromEntries(Object.entries(elements).map(([key, node]) => [key, serialize(node)]))));

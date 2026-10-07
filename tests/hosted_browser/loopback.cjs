// Preload in the isolated Playwright run so Node API clients, like Chromium,
// resolve only these reserved test hostnames to loopback without public DNS.
const dns = require("node:dns");
const hostname = (name) =>
  ["full.localhost", "demo.localhost"].includes(name) ? "127.0.0.1" : name;
const lookup = dns.lookup;
dns.lookup = (name, ...args) => lookup(hostname(name), ...args);
const promiseLookup = dns.promises.lookup;
dns.promises.lookup = (name, ...args) => promiseLookup(hostname(name), ...args);

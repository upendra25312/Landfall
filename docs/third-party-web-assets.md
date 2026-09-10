# Third-party browser assets

DOMPurify 3.4.14 is vendored as `src/web/static/purify.min.js` from the
[official release](https://github.com/cure53/DOMPurify/tree/3.4.14), under the
[Apache 2.0 license](DOMPurify-LICENSE). SHA-256:
`c2f26ea4fc0d88141c9aa430eb515ac86fce59418ceebd85fa475b87a8d6c3e6`.

The dashboard uses it at every nonempty HTML sink. It strips event handlers,
dangerous URL schemes, inline styles and embedded frames before DOM insertion.
Trusted external JavaScript applies an allowlist of layout properties afterwards;
URL/expression declarations are rejected. No runtime CDN dependency is required.
JavaScript syntax and vendored-byte integrity are checked in CI. Review upstream
security fixes before updating the pinned release and hash together.

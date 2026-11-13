/**
 * Renders text with optional furigana. `segments` come from the backend
 * (exercise.annotations, see tracks/japanese_text.py): an array of
 * { text, reading?, focus? } whose texts concatenate to the original string.
 * `focus` marks the word the exercise is about (underlined). Without
 * segments the plain text is rendered; with furigana hidden, segments are
 * still used for the focus underline.
 */
export function RubyText({ text, segments, showFurigana = true }) {
  if (!segments?.length) return <>{text}</>;
  return (
    <>
      {segments.map((seg, i) => {
        const content = seg.reading && showFurigana
          ? <ruby>{seg.text}<rt style={rtStyle}>{seg.reading}</rt></ruby>
          : seg.text;
        return <span key={i} style={seg.focus ? focusStyle : undefined}>{content}</span>;
      })}
    </>
  );
}

const rtStyle = { fontSize: "0.55em", fontWeight: 400, opacity: 0.85, letterSpacing: 0 };
const focusStyle = {
  textDecoration: "underline",
  textDecorationColor: "var(--accent)",
  textDecorationThickness: "2px",
  textUnderlineOffset: "6px",
  color: "var(--accent-light)",
};

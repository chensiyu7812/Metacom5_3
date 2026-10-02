// Presentation-only supplement: expose the already-bound current cutoff date.
// Does not change items, sources, labels, encryption or form identities.
function showCurrentCutDate() {
  const source = form.sources[form.items[current].source_key];
  $('current').previousElementSibling.textContent =
    '当前对话（' + source.current_date + '，截止待回复位置）';
}
for (const id of ['prev', 'next']) $(id).addEventListener('click', showCurrentCutDate);
$('nav').addEventListener('change', showCurrentCutDate);
showCurrentCutDate();

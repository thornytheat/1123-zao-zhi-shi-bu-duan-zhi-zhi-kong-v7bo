function drawProjectChart(target, points) {
    const report = named('ol',undefined,'specimen-register');
    const maximum = Math.max(1, ...points.map(row => Math.abs(row.value)));
    for (const point of points) {
        const entry = named('li');
        const meter = named('meter');
        meter.min = 0; meter.max = maximum; meter.value = Math.abs(point.value);
        meter.setAttribute('aria-label', point.label);
        entry.append(named('span',point.label),meter,named('strong',point.value));
        report.append(entry);
    }
    target.append(report);
}

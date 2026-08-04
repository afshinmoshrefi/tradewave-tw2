import fs from 'fs';
import path from 'path';

test('does not force the seasonal bar chart below native display resolution', () => {
    const source = fs.readFileSync(path.join(__dirname, 'BarChart.js'), 'utf8');

    expect(source).not.toMatch(/devicePixelRatio\s*:\s*(?:0?\.\d+)/);
});

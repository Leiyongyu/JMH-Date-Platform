import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const html = readFileSync(new URL('../public/ebay-tool/index.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const plain = value => JSON.parse(JSON.stringify(value));

function page() {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, { value: '', checked: false, textContent: '', innerHTML: '',
            style: {}, validity: { valid: true }, classList: { add() {}, remove() {}, contains() { return false; } } });
        return elements.get(id);
    };
    const state = { boxes: [] };
    const context = vm.createContext({ URLSearchParams, FormData, Blob, setTimeout,
        window: { location: { search: '' } },
        document: { getElementById: element, addEventListener() {}, querySelector() { return null; },
            querySelectorAll(selector) {
                if (selector.includes('tbody input')) return state.boxes;
                return [];
            } },
        fetch: async () => ({ ok: true, json: async () => ({ configured: true }) })
    });
    vm.runInContext(script, context); // also verifies syntax of the complete deployed inline script
    return { context, element, state, run: code => vm.runInContext(code, context) };
}

const groups = [{ oe: 'a', items: [
    { _selectionKey: 0, itemId: 'a0', pf: 30, title: 'BMW original', sellerFeedback: '99.5', shipping: '免运费', estimatedSold: 4 },
    { _selectionKey: 1, itemId: 'a1', pf: 10, title: 'BMW universal', sellerFeedback: '80', shipping: '2.00 EUR', estimatedSold: 9 },
    { _selectionKey: 2, itemId: 'a2', pf: 20, title: 'BMW part', sellerFeedback: '', shipping: '', estimatedSold: null }
] }, { oe: 'b', items: [
    { _selectionKey: 0, itemId: 'b0', pf: 15, title: 'BMW original', sellerFeedback: '100', shipping: '免运费', estimatedSold: 7 }
] }];

test('filters apply to all OE groups, preserve originals, and relaxing restores rows', () => {
    const { context } = page();
    const original = JSON.stringify(groups);
    const view = context.filterResultGroups(groups, { sort: 'price_asc', minPrice: 15, maxPrice: 35,
        feedback: 95, sold: 4, freeShipping: true, include: 'bmw', exclude: 'UNIVERSAL' });
    assert.deepEqual(plain(view.map(g => g.items.map(i => i.itemId))), [['a0'], ['b0']]);
    assert.equal(JSON.stringify(groups), original);
    assert.equal(context.filterResultGroups(groups, { sort: 'price_asc' })[0].items.length, 3);
});

test('four sorts are numeric and missing metrics sort last', () => {
    const { context } = page();
    for (const [sort, expected] of Object.entries({ price_asc: ['a1', 'a2', 'a0'],
        price_desc: ['a0', 'a2', 'a1'], sold_desc: ['a1', 'a0', 'a2'], feedback_desc: ['a0', 'a1', 'a2'] })) {
        assert.deepEqual(plain(context.filterResultGroups(groups, { sort })[0].items.map(i => i.itemId)), expected);
    }
    assert.equal(context.filterResultGroups(groups, { sort: 'price_asc', sold: 0 })[0].items.length, 2);
});

test('all-missing sales disables controls, clears stale limits and restores price sort', () => {
    const { context, run, element } = page();
    context.inputGroups = [{ oe: 'a', items: [
        { _selectionKey: 0, pf: 20, estimatedSold: null },
        { _selectionKey: 1, pf: 10, estimatedSold: '' }
    ] }];
    run('rawResultsData = {results: inputGroups};');
    element('filter-sold').value = '5';
    element('filter-sort').value = 'sold_desc';
    context.syncSoldFilterAvailability();
    assert.equal(element('filter-sold').disabled, true);
    assert.equal(element('filter-sort-sold').disabled, true);
    assert.equal(element('filter-sold').value, '');
    assert.equal(element('filter-sort').value, 'price_asc');
    assert.match(element('filter-sold-hint').textContent, /本次查询无销量数据/);
    assert.deepEqual(plain(context.filterResultGroups(context.inputGroups, { sold: 5, sort: 'sold_desc' })[0].items.map(i => i.pf)), [10, 20]);
});

test('availability uses all raw OE groups, zero is valid and new results re-enable controls', () => {
    const { context, run, element } = page();
    run('rawResultsData = {results: []};');
    context.syncSoldFilterAvailability();
    assert.equal(element('filter-sold').disabled, true);
    context.inputGroups = [{ oe: 'a', items: [{ estimatedSold: null }] },
        { oe: 'b', items: [{ estimatedSold: '0' }] }];
    run('rawResultsData = {results: inputGroups}; allResultsData = {results: []};');
    context.syncSoldFilterAvailability();
    assert.equal(element('filter-sold').disabled, false);
    assert.equal(element('filter-sort-sold').disabled, false);
    assert.equal(element('filter-sold-hint').textContent, '');
    assert.deepEqual(plain(context.filterResultGroups(context.inputGroups, { sold: 0, sort: 'sold_desc' }).map(g => g.items.length)), [0, 1]);
    for (const estimatedSold of [null, undefined, '', ' ', 'invalid', Infinity, NaN]) {
        assert.equal(context.hasSoldData([{ items: [{ estimatedSold }] }]), false);
    }
});

test('missing sales never removes visible export selections when another filter changes', () => {
    const { context, run, element, state } = page();
    context.inputGroups = groups.map(group => ({ ...group,
        items: group.items.map(item => ({ ...item, estimatedSold: null })) }));
    run('rawResultsData = {results: inputGroups}; allResultsData = rawResultsData; oeSelections = {a:[0,1,2], b:[0]};');
    state.boxes = [0, 1, 2].map(idx => ({ checked: true, dataset: { idx: String(idx) } }));
    context.showOe = () => { state.boxes = []; };
    element('filter-sold').value = '50';
    element('filter-sort').value = 'sold_desc';
    context.applyResultFilters();
    assert.deepEqual(plain(run('oeSelections')), { a: [0, 1, 2], b: [0] });
    // The real renderer recreates the selected checkboxes before export reads them.
    state.boxes = [1, 2, 0].map(idx => ({ checked: true, dataset: { idx: String(idx) } }));
    assert.deepEqual(plain(context.getCheckedItems().map(item => item.itemId)), ['a1', 'a2', 'a0', 'b0']);
});

test('render initializes sales availability for every new response', () => {
    const { context, element } = page();
    context.showOe = () => {};
    context.renderResults([{ oe: 'a', items: [{ pf: 10, estimatedSold: null }] }]);
    assert.equal(element('filter-sold').disabled, true);
    context.renderResults([{ oe: 'a', items: [{ pf: 10, estimatedSold: 0 }] }]);
    assert.equal(element('filter-sold').disabled, false);
});

test('selected identity survives sort and export follows visible order across OE groups', () => {
    const { context, run, state } = page();
    context.inputGroups = groups;
    run("allResultsData = { results: filterResultGroups(inputGroups, {sort: 'price_asc'}) }; oeSelections = {a: [0, 1], b: [0]};");
    state.boxes = [0, 1].map(idx => ({ checked: true, dataset: { idx: String(idx) } }));
    assert.deepEqual(plain(context.getCheckedItems().map(item => item.itemId)), ['a1', 'a0', 'b0']);
    assert.equal('_selectionKey' in context.getCheckedItems()[0], false);
});

test('applying filters prunes hidden selections and reset does not reselect them', () => {
    const { context, run, element, state } = page();
    context.inputGroups = groups;
    run("rawResultsData = {results: inputGroups}; allResultsData = rawResultsData; oeSelections = {a: [0,1,2], b:[0]};");
    state.boxes = [0, 1, 2].map(idx => ({ checked: true, dataset: { idx: String(idx) } }));
    context.showOe = () => { state.boxes = []; };
    element('filter-max').value = '20';
    element('filter-sort').value = 'price_desc';
    context.applyResultFilters();
    assert.deepEqual(plain(run('oeSelections')), { a: [1, 2], b: [0] });
    state.boxes = [1, 2].map(idx => ({ checked: true, dataset: { idx: String(idx) } }));
    element('filter-max').value = '';
    context.applyResultFilters();
    assert.equal(run('allResultsData.results[0].items.length'), 3);
    assert.deepEqual(plain(run('oeSelections')), { a: [1, 2], b: [0] });
    assert.equal(run('rawResultsData.results[0].items.length'), 3);
});

for (const upload of [false, true]) {
    for (const failure of ['submit400', 'missingTask', 'poll404', 'invalidJson', 'taskError']) {
        test(`${upload ? 'file' : 'manual'} search stops on ${failure} without polling undefined`, async () => {
            const { context, run, element } = page();
            const requests = [];
            context.fetch = async url => {
                requests.push(url);
                if (failure === 'invalidJson') return { ok: false, status: 502, json: async () => { throw Error('html'); } };
                const poll = url.includes('/status/');
                const data = poll ? failure === 'poll404' ? { detail: '任务未找到' } : { status: 'error', msg: '搜索失败' }
                    : failure === 'submit400' ? { detail: '请输入至少一个产品编号' }
                    : failure === 'missingTask' ? {} : { task_id: 'valid-task' };
                return { ok: !['submit400', 'poll404'].includes(failure), status: poll ? 404 : 400, json: async () => data };
            };
            // Only poll404 is a successful submission followed by a failed poll.
            const fetch = context.fetch;
            if (failure === 'poll404') context.fetch = async url => url.includes('/status/') ? fetch(url)
                : (requests.push(url), { ok: true, status: 200, json: async () => ({ task_id: 'valid-task' }) });
            context.sleep = async () => {};
            run("nkwDraft = 'BMW-30013'; selectedFile = new Blob(['fixture']);");
            await (upload ? context.doScrapeFile() : context.doScrape());
            assert.ok(element('status').textContent);
            assert.equal(requests.length, ['poll404', 'taskError'].includes(failure) ? 2 : 1);
            assert.ok(requests.every(url => !url.includes('undefined')));
            assert.equal(element(upload ? 'btn-file' : 'btn').disabled, false);
        });
    }
}

test('invalid task IDs are rejected before polling', () => {
    const { context } = page();
    for (const task_id of [undefined, null, '', ' ', 'undefined', 'null', 123]) {
        assert.throws(() => context.requireTaskId({ task_id }), /task_id/);
    }
    assert.equal(context.requireTaskId({ task_id: 'valid/task' }), 'valid%2Ftask');
});

for (const upload of [false, true]) {
    test(`${upload ? 'file' : 'manual'} successful search still renders results`, async () => {
        const { context, run, element } = page();
        let rendered;
        context.fetch = async url => ({ ok: true, status: 200, json: async () =>
            url.includes('/status/') ? { status: 'done', results: groups }
                : { task_id: 'valid-task', sku_mapping: { SKU: 'a' } } });
        context.sleep = async () => {};
        context.renderResults = (results, mapping) => { rendered = { results, mapping }; };
        run("nkwDraft = 'BMW-30013'; selectedFile = new Blob(['fixture']);");
        await (upload ? context.doScrapeFile() : context.doScrape());
        assert.deepEqual(plain(rendered), { results: groups, mapping: { SKU: 'a' } });
        assert.equal(element(upload ? 'btn-file' : 'btn').disabled, false);
    });
}

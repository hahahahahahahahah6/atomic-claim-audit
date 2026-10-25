import argparse
import json
import sys
from . import __version__
from .audit import audit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, '%s: error: %s\n' % (self.prog, message))


def main(argv=None):
    parser = Parser(description='Offline audit of documented atomic-write claims.')
    parser.add_argument('path', nargs='?', default='.')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[], metavar='GLOB')
    parser.add_argument('--fail-on', choices=['MEDIUM', 'HIGH'], default='MEDIUM')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    try:
        report = audit(args.path, args.ignore)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if report['errors']:
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            for error in report['errors']:
                print('%s: %s' % (error['path'], error['message']), file=sys.stderr)
        return 1
    failed = any(f['severity'] == 'HIGH' or args.fail_on == 'MEDIUM' for f in report['findings'])
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print('FAIL' if failed else 'PASS')
        for finding in report['findings']:
            print('%s %s' % (finding['severity'], finding['rule']))
            for item in finding['evidence']:
                print('  %s:%s %s' % (item['path'], item['line'], item['kind']))
        if args.verbose:
            for claim in report['verified_claims']:
                print('Verified: ' + claim['family'])
    return 2 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

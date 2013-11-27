from django.views.decorators.csrf import csrf_exempt
from rest_framework import mixins, status
from rest_framework.generics import RetrieveAPIView, ListAPIView, get_object_or_404, UpdateAPIView
from rest_framework.response import Response
from concepts.models import Concept, ConceptVersion
from concepts.serializers import ConceptCreateSerializer, ConceptListSerializer, ConceptDetailSerializer, ConceptVersionListSerializer, ConceptVersionDetailSerializer, ConceptVersionUpdateSerializer
from oclapi.permissions import HasAccessToVersionedObject
from oclapi.views import SubResourceMixin, VersionedResourceChildMixin
from sources.models import SourceVersion


class ConceptBaseView(SubResourceMixin):
    lookup_field = 'concept'
    pk_field = 'mnemonic'
    model = Concept
    queryset = Concept.objects.filter(is_active=True)
    permission_classes = (HasAccessToVersionedObject,)
    child_list_attribute = 'concepts'


class ConceptRetrieveUpdateDestroyView(ConceptBaseView, RetrieveAPIView, UpdateAPIView):
    serializer_class = ConceptDetailSerializer

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        if request.method != 'PUT':
            self.kwargs = kwargs
            self.request = self.initialize_request(request, *args, **kwargs)
            self.initial(self.request, *args, **kwargs)
            concept = self.get_object()
            kwargs.update({'versioned_object': concept})
            delegate_view = ConceptVersionRetrieveView.as_view()
            return delegate_view(request, *args, **kwargs)
        return super(ConceptRetrieveUpdateDestroyView, self).dispatch(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.serializer_class = ConceptVersionUpdateSerializer
        partial = kwargs.pop('partial', True)
        self.object = self.get_object_or_none()

        if self.object is None:
            return Response({'non_field_errors': 'Could not find concept to update'}, status=status.HTTP_404_NOT_FOUND)
        else:
            latest_version = ConceptVersion.get_latest_version_of(self.object)
            self.object = latest_version.clone()
            save_kwargs = {'force_update': False}
            success_status_code = status.HTTP_200_OK

        serializer = self.get_serializer(self.object, data=request.DATA,
                                         files=request.FILES, partial=partial)

        if serializer.is_valid():
            self.pre_save(serializer.object)
            self.object = serializer.save(**save_kwargs)
            if serializer.is_valid():
                self.post_save(self.object, created=True)
                return Response(serializer.data, status=success_status_code)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConceptListView(ListAPIView):
    model = Concept
    queryset = Concept.objects.filter(is_active=True)
    serializer_class = ConceptListSerializer


class ConceptCreateView(ConceptBaseView,
                        mixins.CreateModelMixin):

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        if request.method != 'POST':
            delegate_view = ConceptVersionListView.as_view()
            return delegate_view(request, *args, **kwargs)
        return super(ConceptCreateView, self).dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.serializer_class = ConceptCreateSerializer
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.DATA, files=request.FILES)
        if serializer.is_valid():
            self.pre_save(serializer.object)
            save_kwargs = {
                'force_insert': True,
                'owner': request.user,
                'parent_resource': self.parent_resource,
                'child_list_attribute': self.child_list_attribute
            }
            self.object = serializer.save(**save_kwargs)
            if serializer.is_valid():
                self.post_save(self.object, created=True)
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED,
                                headers=headers)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConceptVersionsView(SubResourceMixin, ListAPIView):
    serializer_class = ConceptVersionListSerializer

    def get_queryset(self):
        return ConceptVersion.objects.filter(versioned_object_id=self.parent_resource.id)


class ConceptVersionBaseView(VersionedResourceChildMixin):
    lookup_field = 'concept_version'
    pk_field = 'mnemonic'
    model = ConceptVersion
    parent_resource_version_model = SourceVersion
    queryset = ConceptVersion.objects.filter(is_active=True)
    permission_classes = (HasAccessToVersionedObject,)
    child_list_attribute = 'concepts'


class ConceptVersionListView(ConceptVersionBaseView, ListAPIView):
    serializer_class = ConceptVersionListSerializer


class ConceptVersionRetrieveView(ConceptVersionBaseView, RetrieveAPIView):
    serializer_class = ConceptVersionDetailSerializer
    versioned_object = None

    def initialize(self, request, path_info_segment, **kwargs):
        self.versioned_object = kwargs.pop('versioned_object', None)
        super(ConceptVersionRetrieveView, self).initialize(request, path_info_segment, **kwargs)

    def get_object(self, queryset=None):
        if self.versioned_object:
            queryset = self.get_queryset()
            filter_kwargs = {'versioned_object_id': self.versioned_object.id}
            return get_object_or_404(queryset, **filter_kwargs)
        return super(ConceptVersionRetrieveView, self).get_object()
